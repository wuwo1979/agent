# A2A 协议规范与实战指南

> Google Agent-to-Agent Protocol - 智能体之间的"通用语言"

---

## 一、A2A 协议概述

### 1.1 背景与定位

A2A（Agent-to-Agent）是 Google 于 2025 年 4 月联合 50+ 合作伙伴推出的开放协议，2025 年 6 月捐赠给 Linux 基金会，2026 年 3 月发布 v1.0 正式版。

| 协议 | 核心场景 | 类比 | 主导方 |
|------|----------|------|--------|
| **MCP** | Agent ↔ Tool | USB（设备连接） | Anthropic |
| **A2A** | Agent ↔ Agent | HTTP（网页互通） | Google |
| **AG-UI** | Agent ↔ User | Web UI | CopilotKit |

### 1.2 解决的核心问题

MCP 解决的是"Agent 怎么用工具"，A2A 解决的是"Agent 之间怎么协作"。

```
传统 M×N 问题：
  Agent A ──定制适配──→ Agent B
  Agent A ──定制适配──→ Agent C
  Agent B ──定制适配──→ Agent C
  → N 个 Agent 需要 N×(N-1) 套胶水代码

A2A 方案：
  Agent A ──A2A──→ Agent B
  Agent A ──A2A──→ Agent C
  Agent B ──A2A──→ Agent C
  → 所有 Agent 统一通过 A2A 通信
```

### 1.3 2026 生态数据

- 150+ 组织支持（Google, Microsoft, AWS, Salesforce, SAP, Atlassian）
- Python/JS/Java/Go 全语言 SDK
- 金融、供应链、IT 运维等生产落地
- 微软 Copilot 平台全面支持 A2A + MCP

---

## 二、核心概念

### 2.1 Agent Card（智能体名片）

每个 Agent 通过 `/.well-known/agent.json` 公开自己的"名片"：

```json
{
  "name": "Data Analysis Agent",
  "description": "Specialized in data analysis and visualization",
  "url": "https://agent.example.com/a2a",
  "version": "1.0.0",
  "capabilities": {
    "streaming": true,
    "pushNotifications": true
  },
  "skills": [
    {
      "id": "data_analysis",
      "name": "Data Analysis",
      "description": "Analyze datasets and generate insights",
      "inputModes": ["text", "file"],
      "outputModes": ["text", "file"]
    }
  ],
  "authentication": {
    "schemes": ["bearer", "oauth2"]
  },
  "defaultInputModes": ["text", "file"],
  "defaultOutputModes": ["text", "file"]
}
```

### 2.2 关键实体

| 实体 | 说明 |
|------|------|
| **Agent Card** | 智能体的"名片"，描述能力、端点、认证方式 |
| **Task** | 一次有状态的协作任务，有完整生命周期 |
| **Message** | Task 内的一次发言（user/agent） |
| **Part** | Message 的最小单元（text/file/structured data） |
| **Artifact** | Task 产出的成果物 |
| **Skill** | Agent 声明的某项能力 |

### 2.3 任务状态机

```
submitted → working → input-required ──┐
    │                                    │
    ├──→ completed                       │
    ├──→ failed                          │
    ├──→ canceled                        │
    └──→ rejected  ←─────────────────────┘
```

### 2.4 角色模型

- **Client Agent（客户端）**：任务发起方（如规划 Agent）
- **Server Agent（服务端）**：任务执行方（如数据/代码 Agent）
- **同一 Agent 可兼任 Client/Server**，动态组队

---

## 三、协议规范

### 3.1 传输与格式

- 底层：HTTP(S)
- Payload：JSON-RPC 2.0
- 流式推送：Server-Sent Events (SSE)
- 认证：API Key / OAuth 2.0 / mTLS / DID/VC

### 3.2 核心方法

| 方法 | 作用 | 本项目映射 |
|------|------|-----------|
| `message/send` | 同步发送消息 | `SupervisorAgent._delegate_to_*` |
| `message/stream` | 流式发送（SSE） | `SupervisorAgent.run_streaming()` |
| `tasks/get` | 查询任务状态 | `SnapshotManager.load()` |
| `tasks/cancel` | 取消任务 | `TaskStatus.CANCELED` |
| `tasks/pushNotificationConfig/set` | 配置 Webhook 推送 | `agents/validator.py` 回调 |
| `tasks/resubscribe` | 断线重新订阅 | `Checkpointer` 恢复 |

### 3.3 请求/响应示例

```json
// 请求：发送任务
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "method": "message/send",
  "params": {
    "message": {
      "role": "user",
      "parts": [
        {"kind": "text", "text": "Analyze this sales data and generate a report"}
      ],
      "messageId": "msg-001"
    }
  }
}

// 响应：任务创建
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "result": {
    "id": "task-abc",
    "status": {"state": "working"},
    "artifacts": []
  }
}
```

---

## 四、A2A 与 MCP 的关系

### 4.1 互补不冲突

```
┌─────────────────────────────────────────────────┐
│                   A2A Layer                       │
│         Agent ↔ Agent Communication              │
├─────────────────────────────────────────────────┤
│                   MCP Layer                       │
│         Agent ↔ Tool Integration                 │
├─────────────────────────────────────────────────┤
│              Agent Runtime Layer                  │
│    LangGraph / Supervisor-Worker / Retry         │
└─────────────────────────────────────────────────┘
```

### 4.2 关键区别

| 维度 | MCP | A2A |
|------|-----|-----|
| 通信对象 | Agent → Tool | Agent → Agent |
| 状态 | 无状态（单次调用） | 有状态（Task 生命周期） |
| 交互模式 | 请求/响应 | 请求/响应 + 流式 + 推送 + 订阅 |
| 能力发现 | `tools/list` | Agent Card（`/.well-known/agent.json`） |
| 任务管理 | 无 | Task 创建/查询/取消/订阅 |
| 认证 | OAuth 2.0 | OAuth 2.0 + mTLS + DID/VC |

### 4.3 在本项目中的应用

| 本项目组件 | 对应协议 | 说明 |
|-----------|---------|------|
| `mcp_gateway/protocol.py` | MCP | 工具注册/调用/返回 |
| `agent_scheduler/supervisor.py` | A2A 概念 | Supervisor-Worker Handoffs |
| `agent_scheduler/state.py` | A2A Task | Task 状态管理 + 快照 |
| `agent_scheduler/graph.py` | Orchestration | LangGraph 编排层 |

---

## 五、实战：A2A 风格的 Supervisor-Worker

### 5.1 架构设计

```python
# agent_scheduler/supervisor.py - A2A 风格实现

class SupervisorAgent:
    """
    Supervisor 相当于 A2A 的 Client Agent
    Workers 相当于 A2A 的 Server Agent
    _delegate_to_* 相当于 A2A 的 message/send
    run_streaming 相当于 A2A 的 message/stream
    """

    async def run(self, state: AgentState) -> AgentState:
        # Phase 1: 派发任务给 Planner Worker
        state = await self._delegate_to_planner(state)
        # Phase 2: 派发任务给 Executor Worker
        state = await self._delegate_to_executor(state)
        # Phase 3: 派发任务给 Validator Worker
        state = await self._delegate_to_validator(state)
        return state

    async def run_streaming(self, state: AgentState):
        """流式派发（A2A message/stream）"""
        yield {"status": "started", "role": "supervisor", "progress": 0.0}
        yield {"status": "running", "role": "planner", "progress": 0.1}
        state = await self._delegate_to_planner(state)
        yield {"status": "completed", "role": "planner", "progress": 0.3}
        # ... executor, validator ...
```

### 5.2 Agent Card 概念

```python
# 概念性 Agent Card（可扩展为实际 A2A 端点）
AGENT_CARD = {
    "name": "MCP Agent Gateway",
    "description": "Multi-agent system with MCP tool integration",
    "url": "http://localhost:9090/mcp",
    "version": "3.0.0",
    "capabilities": {
        "streaming": True,
        "pushNotifications": False,
    },
    "skills": [
        {
            "id": "task_decomposition",
            "name": "Task Decomposition",
            "description": "Break complex tasks into executable subtasks",
        },
        {
            "id": "parallel_execution",
            "name": "Parallel Tool Execution",
            "description": "Execute independent tools in parallel with topological sort",
        },
        {
            "id": "result_validation",
            "name": "Result Validation",
            "description": "Validate execution results and suggest improvements",
        },
    ],
    "authentication": {
        "schemes": ["bearer"],
    },
}
```

---

## 六、2026 年 Agent 协议栈全景

```
┌──────────────────────────────────────────────────────────┐
│                     Application Layer                      │
│               User Interface / API Gateway                 │
├──────────────────────────────────────────────────────────┤
│                    AG-UI (Agent ↔ User)                   │
│            CopilotKit: Interactive Agent UI                │
├──────────────────────────────────────────────────────────┤
│                    A2A (Agent ↔ Agent)                    │
│       Google: Task-based multi-agent collaboration        │
├──────────────────────────────────────────────────────────┤
│                    MCP (Agent ↔ Tool)                     │
│    Anthropic: Tool discovery, invocation, and results     │
├──────────────────────────────────────────────────────────┤
│                  Orchestration Layer                       │
│    LangGraph / CrewAI / AutoGen / Semantic Kernel         │
├──────────────────────────────────────────────────────────┤
│                  Infrastructure Layer                      │
│    Docker / K8s / Cloud Run / Serverless                  │
└──────────────────────────────────────────────────────────┘
```

---

## 七、常见问题

**Q: A2A 和 MCP 应该选哪个？**

A: 不是二选一，是互补。Agent 调用工具用 MCP，Agent 之间协作用 A2A。生产系统中常常一起使用。

**Q: 本项目和 A2A 的关系？**

A: 本项目的 Supervisor-Worker 模式本质上实现了 A2A 的核心概念（任务派发、状态管理、Handoffs），虽然未直接使用 A2A SDK，但架构设计完全兼容 A2A 协议规范。

**Q: 如何从 Supervisor-Worker 迁移到 A2A？**

A: 将 `_delegate_to_*` 方法替换为 A2A 的 `message/send` 调用，将 `AgentState` 映射为 A2A 的 `Task`，添加 `/.well-known/agent.json` 端点即可。