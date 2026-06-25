"""
Agent 调度层 - 规划 Agent
负责将用户输入拆解为可执行的子任务 DAG
"""

import json
import logging
import uuid

from agent_scheduler.state import AgentState, SubTask, TaskStatus

logger = logging.getLogger("agent_scheduler.planner")

# Optional langchain imports
try:
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI
    _LANGCHAIN_AVAILABLE = True
except ImportError:
    _LANGCHAIN_AVAILABLE = False
    HumanMessage = None
    SystemMessage = None
    ChatOpenAI = None

PLANNER_SYSTEM_PROMPT = """你是一个任务规划专家。你的职责是将用户的复杂任务拆解为可执行的子任务。

## 规则
1. 分析用户输入，识别需要执行的具体步骤
2. 每个子任务必须对应一个可用的工具调用
3. 明确子任务之间的依赖关系
4. 尽可能让无依赖的子任务可以并行执行

## 可用工具
{tools_description}

## 输出格式
请严格按照以下 JSON 格式输出（不要包含其他内容）：
```json
{{
  "plan": [
    {{
      "id": "task_1",
      "description": "任务描述",
      "tool_name": "工具名称",
      "arguments": {{}},
      "dependencies": []
    }}
  ],
  "reasoning": "规划思路说明"
}}
```

## 示例
用户输入：读取 config.json 文件并查询数据库中的用户表
计划：
```json
{{
  "plan": [
    {{
      "id": "task_1",
      "description": "读取 config.json 文件",
      "tool_name": "fs_read_file",
      "arguments": {{"path": "config.json"}},
      "dependencies": []
    }},
    {{
      "id": "task_2",
      "description": "查询数据库用户表",
      "tool_name": "db_query",
      "arguments": {{"sql": "SELECT * FROM users"}},
      "dependencies": []
    }}
  ],
  "reasoning": "两个任务无依赖关系，可以并行执行"
}}
```
"""


class PlannerAgent:
    """
    规划 Agent
    使用 LLM 将用户意图拆解为子任务 DAG
    """

    def __init__(self, llm: ChatOpenAI, tools_description: str):
        self.llm = llm
        self.tools_description = tools_description

    async def plan(self, state: AgentState) -> AgentState:
        """
        生成执行计划
        Args:
            state: 当前 Agent 状态
        Returns:
            更新后的 Agent 状态（包含 plan）
        """
        logger.info(f"PlannerAgent: planning for task '{state.user_input[:50]}...'")

        state.task_status = TaskStatus.PLANNING
        state.add_message("planner", f"开始规划任务: {state.user_input}")

        # 构建 prompt
        system_prompt = PLANNER_SYSTEM_PROMPT.format(
            tools_description=self.tools_description
        )
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"请规划以下任务：\n{state.user_input}")
        ]

        try:
            response = await self.llm.ainvoke(messages)
            plan_data = self._parse_plan(response.content)

            # 构建 SubTask 列表
            state.plan = []
            for item in plan_data.get("plan", []):
                task = SubTask(
                    id=item.get("id", f"task_{uuid.uuid4().hex[:8]}"),
                    description=item.get("description", ""),
                    tool_name=item.get("tool_name", ""),
                    arguments=item.get("arguments", {}),
                    dependencies=item.get("dependencies", []),
                )
                state.plan.append(task)

            reasoning = plan_data.get("reasoning", "")
            state.add_message("planner", f"规划完成: {reasoning}")
            logger.info(f"PlannerAgent: generated {len(state.plan)} subtasks")

        except Exception as e:
            logger.error(f"PlannerAgent failed: {e}")
            state.add_error(f"规划失败: {e}")
            state.task_status = TaskStatus.FAILED

        return state

    def _parse_plan(self, content: str) -> dict:
        """解析 LLM 输出的规划 JSON"""
        # 提取 JSON 块
        if "```json" in content:
            start = content.index("```json") + 7
            end = content.index("```", start)
            json_str = content[start:end].strip()
        elif "```" in content:
            start = content.index("```") + 3
            end = content.index("```", start)
            json_str = content[start:end].strip()
        else:
            json_str = content.strip()

        return json.loads(json_str)


class SimplePlannerAgent:
    """
    简化版规划 Agent（无需 LLM，基于规则）
    用于演示和测试
    """

    def __init__(self, tools_description: str = ""):
        self.tools_description = tools_description

    async def plan(self, state: AgentState) -> AgentState:
        """基于规则的简单规划"""
        state.task_status = TaskStatus.PLANNING
        user_input = state.user_input.lower()

        state.plan = []

        # 规则匹配
        if "读" in user_input or "read" in user_input:
            # 尝试提取文件路径
            import re
            paths = re.findall(r'["\']?([\w./\\-]+\.\w+)["\']?', state.user_input)
            for i, path in enumerate(paths):
                state.plan.append(SubTask(
                    id=f"task_{i+1}",
                    description=f"读取文件 {path}",
                    tool_name="fs_read_file",
                    arguments={"path": path},
                    dependencies=[],
                ))

        if "查询" in user_input or "query" in user_input or "sql" in user_input.lower():
            state.plan.append(SubTask(
                id=f"task_{len(state.plan)+1}",
                description="执行数据库查询",
                tool_name="db_query",
                arguments={"sql": "SELECT * FROM sqlite_master"},
                dependencies=[],
            ))

        if "系统" in user_input or "system" in user_input or "info" in user_input.lower():
            state.plan.append(SubTask(
                id=f"task_{len(state.plan)+1}",
                description="获取系统信息",
                tool_name="term_sysinfo",
                arguments={},
                dependencies=[],
            ))

        if "命令" in user_input or "command" in user_input or "执行" in user_input:
            state.plan.append(SubTask(
                id=f"task_{len(state.plan)+1}",
                description="执行终端命令",
                tool_name="term_run",
                arguments={"command": "echo hello"},
                dependencies=[],
            ))

        if not state.plan:
            # 默认计划
            state.plan.append(SubTask(
                id="task_1",
                description="获取系统信息",
                tool_name="term_sysinfo",
                arguments={},
                dependencies=[],
            ))

        state.add_message("planner", f"规则规划完成，生成 {len(state.plan)} 个子任务")
        return state
