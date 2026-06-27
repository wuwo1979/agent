# ============================================================
# Stage 1: Build
# ============================================================
FROM python:3.11-slim AS builder

LABEL maintainer="MCP Tool Gateway Team"
LABEL description="MCP 本地工具网关 - HTTP + STDIO 双模，支持 Dify / Trae / Ollama 全链路"

WORKDIR /build

# Install system build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ \
    && rm -rf /var/lib/apt/lists/*

# Install only runtime dependencies
COPY requirements/runtime.txt /build/requirements-runtime.txt
RUN pip install --no-cache-dir --user -r /build/requirements-runtime.txt

# ============================================================
# Stage 2: Runtime
# ============================================================
FROM python:3.11-slim

WORKDIR /app

# Install minimal runtime system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy pre-built dependencies from builder
COPY --from=builder /root/.local /root/.local

# Copy only runtime application code
COPY main.py /app/
COPY mcp_gateway/ /app/mcp_gateway/
COPY core/ /app/core/
COPY performance/ /app/performance/
COPY config/ /app/config/

# Ensure scripts in PATH
ENV PATH=/root/.local/bin:$PATH

# Expose ports
EXPOSE 9090

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:9090/api/v1/health || exit 1

# Default entry
CMD ["python", "main.py", "--host", "0.0.0.0", "--port", "9090"]