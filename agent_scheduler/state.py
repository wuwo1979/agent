"""
Agent 调度层 - 状态管理
基于 LangGraph 的状态定义、快照、断点续跑
"""

from typing import Any, Dict, List, Optional, TypedDict, Annotated
from dataclasses import dataclass, field
from enum import Enum
import json
import os
import time
import pickle
from datetime import datetime
import logging

logger = logging.getLogger("agent_scheduler")


# ============================================================
# 状态定义
# ============================================================

class TaskStatus(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    EXECUTING = "executing"
    VALIDATING = "validating"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentRole(str, Enum):
    PLANNER = "planner"       # 规划 Agent：拆解任务
    EXECUTOR = "executor"    # 执行 Agent：调用工具
    VALIDATOR = "validator"  # 校验 Agent：验证结果


@dataclass
class SubTask:
    """子任务定义"""
    id: str
    description: str
    tool_name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)  # 依赖的子任务 ID
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    execution_time_ms: float = 0.0
    created_at: float = field(default_factory=time.time)


@dataclass
class AgentState:
    """
    Agent 全局状态
    支持序列化/反序列化实现断点续跑
    """
    # 任务信息
    task_id: str = ""
    user_input: str = ""
    task_status: TaskStatus = TaskStatus.PENDING

    # 规划阶段
    plan: List[SubTask] = field(default_factory=list)
    current_step: int = 0

    # 消息历史
    messages: List[Dict[str, Any]] = field(default_factory=list)

    # 执行上下文
    tool_results: Dict[str, Any] = field(default_factory=dict)
    context_cache: Dict[str, Any] = field(default_factory=dict)

    # 校验结果
    validation_result: Optional[Dict[str, Any]] = None
    final_output: Optional[str] = None

    # 性能指标
    start_time: float = 0.0
    end_time: float = 0.0
    total_tokens: int = 0
    successful_tool_calls: int = 0
    failed_tool_calls: int = 0

    # 错误与重试
    errors: List[str] = field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 3

    # 快照版本
    snapshot_version: int = 0

    def add_message(self, role: str, content: str):
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": time.time()
        })

    def add_error(self, error: str):
        self.errors.append(error)
        self.add_message("system", f"Error: {error}")

    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "task_id": self.task_id,
            "user_input": self.user_input,
            "task_status": self.task_status.value,
            "plan": [
                {
                    "id": t.id,
                    "description": t.description,
                    "tool_name": t.tool_name,
                    "arguments": t.arguments,
                    "dependencies": t.dependencies,
                    "status": t.status.value,
                    "result": str(t.result)[:1000] if t.result else None,
                    "error": t.error,
                    "retry_count": t.retry_count,
                    "execution_time_ms": t.execution_time_ms,
                }
                for t in self.plan
            ],
            "current_step": self.current_step,
            "messages": self.messages[-20:],  # 只保留最近 20 条
            "tool_results": {k: str(v)[:500] for k, v in self.tool_results.items()},
            "validation_result": self.validation_result,
            "final_output": self.final_output,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "total_tokens": self.total_tokens,
            "successful_tool_calls": self.successful_tool_calls,
            "failed_tool_calls": self.failed_tool_calls,
            "errors": self.errors[-10:],
            "retry_count": self.retry_count,
            "snapshot_version": self.snapshot_version,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AgentState":
        """从字典恢复"""
        state = cls()
        state.task_id = data.get("task_id", "")
        state.user_input = data.get("user_input", "")
        state.task_status = TaskStatus(data.get("task_status", "pending"))
        state.current_step = data.get("current_step", 0)
        state.messages = data.get("messages", [])
        state.validation_result = data.get("validation_result")
        state.final_output = data.get("final_output")
        state.start_time = data.get("start_time", 0.0)
        state.end_time = data.get("end_time", 0.0)
        state.total_tokens = data.get("total_tokens", 0)
        state.successful_tool_calls = data.get("successful_tool_calls", 0)
        state.failed_tool_calls = data.get("failed_tool_calls", 0)
        state.errors = data.get("errors", [])
        state.retry_count = data.get("retry_count", 0)
        state.snapshot_version = data.get("snapshot_version", 0)

        # 恢复子任务
        for t_data in data.get("plan", []):
            task = SubTask(
                id=t_data["id"],
                description=t_data["description"],
                tool_name=t_data["tool_name"],
                arguments=t_data.get("arguments", {}),
                dependencies=t_data.get("dependencies", []),
                status=TaskStatus(t_data["status"]),
                result=t_data.get("result"),
                error=t_data.get("error"),
                retry_count=t_data.get("retry_count", 0),
                execution_time_ms=t_data.get("execution_time_ms", 0.0),
            )
            state.plan.append(task)

        return state


# ============================================================
# 状态快照管理器（断点续跑）
# ============================================================

class SnapshotManager:
    """
    状态快照管理器
    支持自动保存/恢复状态，实现断点续跑
    """

    def __init__(self, snapshot_dir: str = "./snapshots"):
        self.snapshot_dir = snapshot_dir
        os.makedirs(snapshot_dir, exist_ok=True)

    def save(self, state: AgentState) -> str:
        """保存状态快照"""
        state.snapshot_version += 1
        filename = f"{state.task_id}_v{state.snapshot_version}.snapshot"
        filepath = os.path.join(self.snapshot_dir, filename)

        snapshot_data = {
            "state": state.to_dict(),
            "timestamp": datetime.now().isoformat(),
            "version": state.snapshot_version,
        }

        with open(filepath, "wb") as f:
            pickle.dump(snapshot_data, f)

        logger.info(f"Snapshot saved: {filepath}")
        return filepath

    def load(self, task_id: str, version: int = -1) -> Optional[AgentState]:
        """加载状态快照（-1 = 最新版本）"""
        snapshots = self._list_snapshots(task_id)
        if not snapshots:
            return None

        if version == -1:
            version = max(snapshots)

        filename = f"{task_id}_v{version}.snapshot"
        filepath = os.path.join(self.snapshot_dir, filename)

        if not os.path.exists(filepath):
            return None

        with open(filepath, "rb") as f:
            data = pickle.load(f)

        state = AgentState.from_dict(data["state"])
        logger.info(f"Snapshot loaded: {filepath}")
        return state

    def _list_snapshots(self, task_id: str) -> List[int]:
        """列出所有快照版本"""
        versions = []
        for f in os.listdir(self.snapshot_dir):
            if f.startswith(task_id) and f.endswith(".snapshot"):
                try:
                    v = int(f.split("_v")[1].split(".")[0])
                    versions.append(v)
                except (IndexError, ValueError):
                    pass
        return sorted(versions)

    def cleanup(self, task_id: str, keep_last: int = 3):
        """清理旧快照"""
        versions = self._list_snapshots(task_id)
        if keep_last == 0:
            remove_list = versions
        elif len(versions) <= keep_last:
            return
        else:
            remove_list = versions[:-keep_last]
        for v in remove_list:
            filepath = os.path.join(self.snapshot_dir, f"{task_id}_v{v}.snapshot")
            os.remove(filepath)