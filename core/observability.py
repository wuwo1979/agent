"""
2026 Observability Module - Metrics Collection & Health Check

Provides structured metrics for the MCP gateway and agent scheduler,
enabling real-time monitoring and OpenTelemetry-compatible export.
"""

import json
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Dict, List


@dataclass
class MetricPoint:
    """Single metric data point"""
    name: str
    value: float
    timestamp: float = field(default_factory=time.time)
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class HealthStatus:
    """Structured health check response"""
    status: str  # "healthy", "degraded", "unhealthy"
    version: str
    uptime_seconds: float
    components: Dict[str, str]
    metrics: Dict[str, float]


class MetricsCollector:
    """Central metrics collector for the entire system"""

    def __init__(self):
        self._counters: Dict[str, int] = defaultdict(int)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._start_time = time.time()

    def increment_counter(self, name: str, value: int = 1):
        """Increment a counter metric"""
        self._counters[name] += value

    def set_gauge(self, name: str, value: float):
        """Set a gauge metric"""
        self._gauges[name] = value

    def record_histogram(self, name: str, value: float):
        """Record a histogram value"""
        self._histograms[name].append(value)

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self._start_time

    def get_counter(self, name: str) -> int:
        return self._counters.get(name, 0)

    def get_gauge(self, name: str) -> float:
        return self._gauges.get(name, 0.0)

    def get_histogram_stats(self, name: str) -> Dict[str, float]:
        values = self._histograms.get(name, [])
        if not values:
            return {"count": 0, "avg": 0, "min": 0, "max": 0, "p95": 0}
        sorted_vals = sorted(values)
        p95_idx = int(len(sorted_vals) * 0.95)
        return {
            "count": len(values),
            "avg": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
            "p95": sorted_vals[min(p95_idx, len(sorted_vals) - 1)],
        }

    def snapshot(self) -> Dict:
        """Return a snapshot of all metrics"""
        return {
            "uptime_seconds": self.uptime_seconds,
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms": {
                name: self.get_histogram_stats(name)
                for name in self._histograms
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.snapshot(), indent=2, ensure_ascii=False)


# Global metrics collector instance
metrics = MetricsCollector()


class HealthChecker:
    """Health check service for all system components"""

    def __init__(self):
        self._components: Dict[str, callable] = {}
        self.version = "2.1.0"

    def register_component(self, name: str, check_fn: callable):
        """Register a component health check function"""
        self._components[name] = check_fn

    async def check_all(self) -> HealthStatus:
        """Run all health checks and return structured status"""
        component_statuses = {}
        all_healthy = True

        for name, check_fn in self._components.items():
            try:
                result = await check_fn() if hasattr(check_fn, '__await__') else check_fn()
                component_statuses[name] = "healthy" if result else "unhealthy"
                if not result:
                    all_healthy = False
            except Exception as e:
                component_statuses[name] = f"error: {str(e)}"
                all_healthy = False

        status = "healthy" if all_healthy else "degraded"

        return HealthStatus(
            status=status,
            version=self.version,
            uptime_seconds=metrics.uptime_seconds,
            components=component_statuses,
            metrics={
                "total_requests": metrics.get_counter("gateway.requests.total"),
                "failed_requests": metrics.get_counter("gateway.requests.failed"),
                "total_tool_calls": metrics.get_counter("tools.calls.total"),
                "cache_hit_rate": metrics.get_gauge("cache.hit_rate"),
                "avg_latency_ms": metrics.get_histogram_stats("gateway.latency")["avg"],
            },
        )

    def to_json(self, health: HealthStatus) -> str:
        return json.dumps(asdict(health), indent=2, ensure_ascii=False)


# Global health checker instance
health_checker = HealthChecker()
