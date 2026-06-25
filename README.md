<p align="center">
  <h1 align="center">MCP Agent Gateway</h1>
  <p align="center">
    <b>让 AI Agent 直接操控本地环境的 MCP 网关</b>
  </p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-blue?style=flat-square&logo=python">
  <img src="https://img.shields.io/badge/MCP-2024--11--05-green?style=flat-square">
  <img src="https://img.shields.io/badge/LangGraph-latest-orange?style=flat-square">
  <img src="https://img.shields.io/badge/license-MIT-brightgreen?style=flat-square">
</p>

---

## 项目定位

### 解决什么问题

AI Agent IDE（如 **Trae、Cursor、Windsurf**）内置的 Agent 只能操作 IDE 沙箱内的文件。当 Agent 需要：

- 读取项目目录外的配置文件
- 执行终端命令（git、docker、构建脚本）
- 查询本地 SQLite 数据库
- 批量处理文件

时必须为每个需求写一遍定制代码。**MCP 协议** 就是为了标准化这个交互而生的。

### 本项目的角色

```
AI Agent IDE (Trae/Cursor/Windsurf)
        │  通过 MCP JSON-RPC 2.0 协议
        ▼
┌─────────────────────────────────────┐
│      MCP Agent Gateway (本项目)      │
│  ┌──────────┐ ┌────────┐ ┌───────┐ │
│  │ filesystem│ │terminal│ │database│ │
│  │ (5 tools)│ │(2 tools)││(4 tools)││
│  └──────────┘ └────────┘ └───────┘ │
│  ┌───────────────────────────────┐  │
│  │ 性能层：缓存 49.5% · 并行 2.8x │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
        │
        ▼
   本地文件系统 / 终端命令 / SQLite 数据库
```

**简单说**：把 MCP 网关架在 AI Agent 和本地工具之间，Agent 通过标准接口调用工具，网关负责安全管控+性能优化。

---

## 快速开始

```bash
git clone https://github.com/wuwo1979/agent.git
cd agent
pip install -r requirements.txt

# 验证核心功能
python demo.py

# 启动网关服务（供 Trae/Cursor 等调用）
python main.py --port 9090

# 运行跑分（含硬件环境信息）
python main.py --benchmark
```

---

## 集成方式

### 方式 1：Trae / Cursor 直接接入

在 Trae 或 Cursor 的 MCP 配置中添加：

```json
{
  "mcpServers": {
    "local-gateway": {
      "url": "http://localhost:9090/mcp",
      "type": "streamable-http"
    }
  }
}
```

配置后，AI Agent 就能直接操作本地文件、执行命令、查询数据库。

### 方式 2：任何 MCP 客户端

```bash
# 使用 curl 模拟 MCP 调用
curl -X POST http://localhost:9090/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"tools/list","params":{}}'

# 列出目录
curl -X POST http://localhost:9090/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"2","method":"tools/call","params":{"name":"list_dir","arguments":{"path":"."}}}'

# 执行命令
curl -X POST http://localhost:9090/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"3","method":"tools/call","params":{"name":"run_command","arguments":{"command":"ls -la","timeout":10}}}'
```

### 方式 3：Python SDK 调用

```python
from mcp_gateway.server import MCPServer

server = MCPServer()
server.register_providers()  # 注册 11 个内置工具
await server.start(port=9090)
```

---

## 11 个内置工具

| Provider | 工具 | 描述 | 安全约束 |
|----------|------|------|----------|
| **filesystem** (5) | `read_file` | 读取文件 | 仅允许项目目录及用户目录（路径隔离） |
| | `write_file` | 写入文件 | 同上 |
| | `list_dir` | 列出目录 | 同上 |
| | `search_files` | 通配符搜索 | 同上 |
| | `file_stat` | 文件元信息 | 同上 |
| **terminal** (2) | `run_command` | 执行命令 | 23 条破坏性命令黑名单 + 可选白名单模式 + 30s 超时 |
| | `sysinfo` | 系统信息 | 只读 |
| **database** (4) | `query` | 查询 | 仅 SELECT/PRAGMA，自动 LIMIT |
| | `execute` | 写操作 | 参数化执行防注入 |
| | `list_tables` | 列表 | 只读 |
| | `describe_table` | 表结构 | 只读 |

---

## 性能指标

> **测试环境**：Windows 11, Python 3.11.5, 4+ cores CPU  
> **测试工具**：Mock（纯内存，无 I/O 抖动）  
> **对比基线**：无缓存串行版本 (no-cache + sequential await)  
> **完整跑分**：`python main.py --benchmark`

| 指标 | 实测值 | 对比基准 | 适用边界 | 说明 |
|------|--------|----------|----------|------|
| Token 压缩率 | **49.5%** | 无缓存全量回传 | 8 次调用含 3 次重复参数 | 增量缓存：重复的工具调用只传增量 |
| 并行加速比 | **2.8x** | 串行逐个执行 | **仅无依赖任务**。6 个独立工具混合耗时 | asyncio.gather vs await 串行 |
| 延迟降低 | **64.4%** | 串行基线 | 同上 | (1 - 并行/串行) × 100% |
| 缓存命中率(全局) | **37.5%** | 全局统计 | 首次 8 次调用含 5 MISS + 3 HIT | 含首次冷启动 |
| 缓存命中率(热) | **66.7%** | 重复调用 | 同一操作连续 3 轮 | 演示脚本中的热场景 |

> **关于并行加速比的边界**：2.8x 加速比仅适用于**无依赖的独立任务并行执行**。对于存在强串行依赖的 DAG 任务（如 A→B→C 必须顺序执行），加速效果受拓扑分层限制，无法达到此值。benchmark 使用 6 个完全独立的工具以显示最大理论加速效果。

---

## 安全设计

### 4 层安全防护

| 层级 | 措施 | 配置方式 |
|------|------|----------|
| **认证** | API Key 验证（X-API-Key header） | `config.yaml` 配置 |
| **限流** | 令牌桶 60 req/min, burst=10 | `config.yaml` 配置 |
| **终端** | 23 条破坏性命令黑名单 + 交互命令拦截 + 可选白名单模式 | `terminal.py` 常量 |
| **文件系统** | 路径隔离（SAFE_ROOTS）+ 路径穿越防护 | `filesystem.py` 常量 |

### 白名单模式（推荐生产用）

启用后仅允许预设的命令前缀：

```python
# mcp_gateway/tools/terminal.py
USE_COMMAND_WHITELIST = True  # 开启白名单模式
ALLOWED_COMMANDS_PREFIXES = [
    "ls", "cat ", "git status", "pwd", "find ", "grep ",
    # ... 详见 terminal.py
]
```

---

## 架构

### 模块职责

| 模块 | 职责 | 依赖性 |
|------|------|--------|
| `mcp_gateway/` | MCP 协议网关（工具注册、调用、JSON-RPC） | **核心**，无额外依赖 |
| `performance/` | 缓存、并行调度、模型适配 | **核心**，无额外依赖 |
| `agent_scheduler/` | LangGraph Agent 调度（Supervisor-Worker） | 可选，需 `pip install langgraph` |
| `vllm_adapter/` | vLLM 推理服务进程管理 | 可选，需 `vllm` |
| `rag/` | ChromaDB 知识库检索 | 可选，需 `chromadb` |

### 目录结构

```
agent/
├── mcp_gateway/          # MCP 协议网关
│   ├── protocol.py       # JSON-RPC + 工具注册
│   ├── transport.py      # HTTP/SSE 传输
│   ├── server.py         # 生产级入口
│   ├── security.py       # 认证 + 限流 + 权限
│   └── tools/            # 11 个内置工具
├── agent_scheduler/      # Agent 调度（可选）
│   ├── graph.py          # LangGraph 工作流
│   ├── supervisor.py     # Supervisor-Worker
│   ├── state.py          # 状态 + 文件快照
│   └── agents/           # Planner + Executor + Validator
├── performance/          # 性能优化
│   ├── cache.py          # 增量上下文缓存
│   ├── parallel.py       # 并行调度 + 拓扑排序
│   └── adapter.py        # 多模型适配
├── core/                 # 基础设施
├── config/               # 配置
├── tests/                # 测试 + 跑分
│   └── benchmark.py      # 5 项性能跑分（含环境信息）
├── examples/             # 集成示例
│   └── integration_demo.py
├── docker/               # Docker 部署
├── demo.py               # 演示脚本
└── main.py               # 主入口
```

---

## 配置

```yaml
# config/config.yaml
mcp:
  host: "0.0.0.0"
  port: 9090
security:
  api_keys: ["your-api-key"]
  rate_limit: 60  # 请求/分钟
  tool_policies:
    terminal.run_command: "deny"  # 禁用终端工具
filesystem:
  safe_roots: ["."]  # 允许的路径
database:
  path: "./data/mcp_gateway.db"
```

---

## 状态持久化

Agent 调度层支持文件快照断点续跑（`pickle` 序列化，默认 `./snapshots/` 目录，保留最近 3 个版本）：

```python
from agent_scheduler.state import SnapshotManager
manager = SnapshotManager("./snapshots")
manager.save(state)                          # 保存快照
state = manager.load("task_001")            # 加载最新
state = manager.load("task_001", version=2) # 加载指定版
```

---

## 可观测性

`core/observability.py` 提供：

- **工具指标**：调用数、成功/失败率、P50/P95/P99 延迟
- **缓存指标**：命中率、节省 Token、缓存条目
- **并行指标**：批次数、加速比、排队时间
- **健康检查**：`GET /health` 返回组件状态
- **日志**：结构化 JSON 格式

---

## 依赖说明

所有依赖附带版本上界锁定（`>=min,<max`）：

```txt
# 核心（必需）
fastapi>=0.115.0,<0.116.0    # HTTP 框架
uvicorn>=0.30.0,<0.31.0       # ASGI 服务器
pydantic>=2.5.0,<3.0.0       # 数据校验

# Agent 调度（可选）
langgraph>=0.2.0,<0.3.0

# RAG（可选）
# chromadb>=0.5.0,<0.6.0     # 按需安装
```

---

## 技术栈

| 类别 | 技术 |
|------|------|
| 协议 | MCP 2024-11-05 + JSON-RPC 2.0 |
| 框架 | FastAPI + Uvicorn |
| 编排 | LangGraph（可选） |
| 模型 | DeepSeek-V4 / OpenAI / Ollama / vLLM |
| 向量库 | ChromaDB（可选） |
| 部署 | Docker Compose |

---

## License

MIT