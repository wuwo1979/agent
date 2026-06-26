"""
Agent 调度层 - 校验 Agent
负责验证任务执行结果、检测异常、生成最终输出
"""

import json
import logging

from mcp_gateway.agents.state import AgentState, TaskStatus

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

logger = logging.getLogger("agent_scheduler.validator")

VALIDATOR_SYSTEM_PROMPT = """你是一个结果校验专家。你的职责是验证任务执行结果的质量。

## 校验规则
1. 检查每个子任务是否成功执行
2. 验证结果是否符合预期
3. 识别异常或错误
4. 给出综合评分（1-10）

## 输出格式
请严格按照以下 JSON 格式输出：
```json
{{
  "valid": true/false,
  "score": 8,
  "issues": ["问题描述1", "问题描述2"],
  "summary": "总结评价",
  "suggestions": ["改进建议1"]
}}
```
"""


class ValidatorAgent:
    """
    校验 Agent
    使用 LLM 验证执行结果质量
    """

    def __init__(self, llm: ChatOpenAI):
        self.llm = llm

    async def validate(self, state: AgentState) -> AgentState:
        """
        验证执行结果
        Args:
            state: 当前 Agent 状态
        Returns:
            更新后的 Agent 状态（包含 validation_result）
        """
        logger.info("ValidatorAgent: validating results...")
        state.task_status = TaskStatus.VALIDATING
        state.add_message("validator", "开始校验执行结果")

        # 构建校验上下文
        execution_summary = self._build_execution_summary(state)
        messages = [
            SystemMessage(content=VALIDATOR_SYSTEM_PROMPT),
            HumanMessage(content=f"""
请校验以下任务执行结果：

## 原始任务
{state.user_input}

## 执行计划
{json.dumps([{'id': t.id, 'description': t.description, 'tool_name': t.tool_name} for t in state.plan], ensure_ascii=False, indent=2)}

## 执行结果
{execution_summary}
""")
        ]

        try:
            response = await self.llm.ainvoke(messages)
            validation = self._parse_validation(response.content)

            state.validation_result = validation
            state.add_message("validator", f"校验完成: 评分={validation.get('score', 'N/A')}")

            if validation.get("valid", False):
                state.final_output = validation.get("summary", "任务完成")
                state.task_status = TaskStatus.COMPLETED
            else:
                state.final_output = f"校验未通过: {validation.get('issues', [])}"
                # 如果校验失败但还有重试次数，可以返回重新规划
                if state.retry_count < state.max_retries:
                    state.task_status = TaskStatus.RETRYING
                    state.add_message("validator", "结果不理想，建议重试")
                else:
                    state.task_status = TaskStatus.COMPLETED  # 不再重试，接受当前结果

        except Exception as e:
            logger.error(f"ValidatorAgent failed: {e}")
            state.add_error(f"校验失败: {e}")
            # 即使校验失败，也标记为完成（不阻塞流程）
            state.task_status = TaskStatus.COMPLETED
            state.validation_result = {
                "valid": True,
                "score": 5,
                "issues": [f"自动校验失败: {e}"],
                "summary": "校验服务异常，默认接受结果",
            }

        return state

    def _build_execution_summary(self, state: AgentState) -> str:
        """构建执行摘要"""
        lines = []
        for task in state.plan:
            status = "✓" if task.status == TaskStatus.COMPLETED else "✗"
            result_str = str(task.result)[:200] if task.result else "N/A"
            error_str = f" (错误: {task.error})" if task.error else ""
            lines.append(
                f"{status} [{task.id}] {task.description}\n"
                f"  工具: {task.tool_name}\n"
                f"  耗时: {task.execution_time_ms:.0f}ms\n"
                f"  结果: {result_str}{error_str}"
            )
        return "\n".join(lines)

    def _parse_validation(self, content: str) -> dict:
        """解析校验结果 JSON"""
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


class SimpleValidator:
    """
    简化版校验器（无需 LLM，基于规则）
    """

    async def validate(self, state: AgentState) -> AgentState:
        """基于规则的简单校验"""
        state.task_status = TaskStatus.VALIDATING

        issues = []
        completed_count = 0
        failed_count = 0

        for task in state.plan:
            if task.status == TaskStatus.COMPLETED:
                completed_count += 1
                # 检查结果是否为空
                if not task.result:
                    issues.append(f"任务 {task.id} 结果为空")
                # 检查是否包含错误信息
                if isinstance(task.result, str) and "error" in task.result.lower():
                    issues.append(f"任务 {task.id} 结果包含错误")
            elif task.status == TaskStatus.FAILED:
                failed_count += 1
                issues.append(f"任务 {task.id} 执行失败: {task.error}")

        score = 10
        if failed_count > 0:
            score -= failed_count * 3
        if issues:
            score -= len(issues)

        valid = failed_count == 0 and len(issues) <= 1

        state.validation_result = {
            "valid": valid,
            "score": max(1, score),
            "issues": issues,
            "summary": f"完成 {completed_count}/{len(state.plan)} 个子任务",
        }

        state.task_status = TaskStatus.COMPLETED
        return state
