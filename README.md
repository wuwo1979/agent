<p align="center">
  <h1 align="center">MCP Agent Gateway</h1>
  <p align="center">
    <b>让 AI Agent 直接操控本地环境的 MCP 网关</b>
  </p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-blue?style=flat-square&logo=python">
  <img src="https://img.shields.io/badge/version-v1.3-brightgreen?style=flat-square">
  <img src="https://img.shields.io/badge/MCP-2024--11--05-green?style=flat-square">
  <img src="https://img.shields.io/badge/LangGraph-compatible-orange?style=flat-square">
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

### 方式 3：Dify 工具接入

在 Dify 工作流中添加 MCP 工具节点，配置为 HTTP 代理：

```yaml
# Dify 自定义工具配置
name: MCP Gateway
endpoint: http://localhost:9090/mcp
schema: |
  {
    "tools": [本网关返回的 tools/list 结果]
  }
```

配置后 Dify 工作流可直接调用本网关的文件操作、终端命令、数据库查询等工具。

### 方式 4：Python SDK 调用

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

## API 接口参考

### HTTP 端点总览

| 端点 | 方法 | 描述 | 认证 |
|------|------|------|------|
| `/mcp` | POST | MCP JSON-RPC 2.0 核心接口 | 可选（X-API-Key） |
| `/health` | GET | 健康检查 + 组件状态 | 无需认证 |
| `/mcp/stats` | GET | 工具调用统计（频率/延迟分位） | 需要 API Key |

所有 MCP 功能请求统一通过 `POST /mcp` 发送 JSON-RPC 消息体，遵循 MCP JSON-RPC 2.0 协议。

### 生命周期

```json
// 请求 → POST /mcp
{"jsonrpc":"2.0","id":"1","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"my-client","version":"1.0"}}}
// 响应 ←
{"jsonrpc":"2.0","id":"1","result":{"protocolVersion":"2024-11-05","serverInfo":{"name":"mcp-gateway","version":"1.3"},"capabilities":{"tools":{},"resources":{},"prompts":{}}}}

// 初始化后发送通知（无响应）
{"jsonrpc":"2.0","id":null,"method":"notifications/initialized","params":{}}
```

### 工具接口

```json
// tools/list - 发现全部工具
// 请求
{"jsonrpc":"2.0","id":"2","method":"tools/list","params":{}}
// 响应
{"jsonrpc":"2.0","id":"2","result":{"tools":[{"name":"read_file","description":"读取文件内容","inputSchema":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}}, ...]}}

// tools/call - 调用具体工具
// 请求
{"jsonrpc":"2.0","id":"3","method":"tools/call","params":{"name":"list_dir","arguments":{"path":"."}}}
// 响应
{"jsonrpc":"2.0","id":"3","result":{"content":[{"type":"text","text":"[\"README.md\", \"main.py\", ...]"}],"isError":false}}
```

### 资源接口

```json
// resources/list - 列出可用资源
{"jsonrpc":"2.0","id":"4","method":"resources/list","params":{}}
// 响应
{"jsonrpc":"2.0","id":"4","result":{"resources":[{"uri":"file:///config/config.yaml","name":"网关配置","mimeType":"text/yaml"}, ...]}}

// resources/read - 读取资源内容
{"jsonrpc":"2.0","id":"5","method":"resources/read","params":{"uri":"file:///config/config.yaml"}}
// 响应
{"jsonrpc":"2.0","id":"5","result":{"contents":[{"uri":"file:///config/config.yaml","mimeType":"text/yaml","text":"mcp:\n  host: \"0.0.0.0\"..."}]}}
```

### 提示模板接口

```json
// prompts/list - 列出提示模板
{"jsonrpc":"2.0","id":"6","method":"prompts/list","params":{}}
// 响应
{"jsonrpc":"2.0","id":"6","result":{"prompts":[{"name":"summarize","description":"总结文件内容","arguments":[{"name":"path","required":true}]}]}}

// prompts/get - 获取提示模板
{"jsonrpc":"2.0","id":"7","method":"prompts/get","params":{"name":"summarize","arguments":{"path":"README.md"}}}
// 响应
{"jsonrpc":"2.0","id":"7","result":{"description":"总结文件内容","messages":[{"role":"user","content":{"type":"text","text":"请总结文件 README.md 的内容"}}]}}
```

### 工具调用异常

```json
// 工具不存在
{"jsonrpc":"2.0","id":"8","error":{"code":-32001,"message":"Tool not found: unknown_tool"}}

// 参数校验失败
{"jsonrpc":"2.0","id":"9","error":{"code":-32602,"message":"Missing required argument: path"}}

// 权限拒绝
{"jsonrpc":"2.0","id":"10","error":{"code":-32005,"message":"Access denied: path outside safe roots"}}
```

---

## 性能指标

> **测试环境**：Windows 11, Python 3.11.5, 4+ cores CPU  
> **测试工具**：Mock（纯内存，无 I/O 抖动）  
> **对比基线**：无缓存串行版本 (no-cache + sequential await)  
> **数据来源**：`python tests/generate_charts.py`（实测自动生成）

### 可视化：串行 vs 并行调度

```mermaid
gantt
    title MCP Gateway 性能基准
    dateFormat  X
    axisFormat  %s

    section 串行执行
    6 工具依次执行  :0, 749.0, 1

    section 并行调度
    6 工具并发执行  :0, 264.7, 1
```

### 对比总览

| 维度 | 基准方案 | MCP Gateway | 提升幅度 |
|------|----------|-------------|----------|
| 多工具调用 | 串行 749.0ms | 并行 264.7ms | [加速] 2.8x |
| 重复上下文 | 完整体积 100% 传输 | 增量缓存命中 43% | [节省] 50% |
| DAG 依赖调度 | 全串行 4 节点 | 分 3 级并行 | [加速] 约 45% 耗时缩减 |

### 详细指标

| 指标 | 实测值 | 对比基准 | 适用边界 | 说明 |
|------|--------|----------|----------|------|
| Token 压缩率 | **50%** | 无缓存全量回传 | 8 次调用含 3 次重复参数 | 增量缓存：重复的工具调用只传增量 |
| 并行加速比 | **2.8x** | 串行逐个执行 | **仅无依赖任务**。6 个独立工具混合耗时 | asyncio.gather vs await 串行 |
| 延迟降低 | **64.4%** | 串行基线 | 同上 | (1 - 并行/串行) × 100% |
| 缓存命中率(全局) | **43%** | 全局统计 | 首次 8 次调用含 5 MISS + 3 HIT | 含首次冷启动 |
| 缓存命中率(热) | **66.7%** | 重复调用 | 同一操作连续 3 轮 | 演示脚本中的热场景 |

> **关于并行加速比的边界**：2.8x 加速比仅适用于**无依赖的独立任务并行执行**。对于存在强串行依赖的 DAG 任务（如 A→B→C 必须顺序执行），加速效果受拓扑分层限制，无法达到此值。benchmark 使用 6 个完全独立的工具以显示最大理论加速效果。

---

## 测试覆盖

> 当前 **30 个注册测试用例**（18 个同步 + 12 个异步），CI 自动执行覆盖率报告并上传 Codecov。

### 核心模块覆盖率目标

| 模块 | 当前覆盖 | 覆盖内容 | CI 门禁(目标) |
|------|----------|----------|---------------|
| `mcp_gateway/protocol.py` | ✅ 协议编解码 | JSON-RPC 解析/响应/通知识别 | ≥85% |
| `mcp_gateway/security.py` | ✅ 安全中间件 | 认证/限流/熔断/权限 | ≥80% |
| `mcp_gateway/tools/*.py` | ⚡ 工具注册 | Provider 注册/注销/调用 | ≥75% |
| `performance/cache.py` | ✅ 上下文缓存 | 缓存命中/未命中/参数差异化 | ≥90% |
| `performance/parallel.py` | ✅ DAG 调度 | 依赖图构建/拓扑排序 | ≥85% |
| `agent_scheduler/state.py` | ✅ 状态管理 | 序列化/快照 | ≥80% |
| `core/interfaces.py` | 🔲 待补 | 基类接口 | ≥70% |

> 运行 `pytest --cov=. --cov-report=html` 后在 `htmlcov/index.html` 查看完整覆盖率报告。

### 测试范围明细

| 测试范围 | 覆盖模块 | 测试项 |
|----------|----------|--------|
| 工具注册 | `mcp_gateway/registry.py` | 注册/注销 provider、工具列表、前缀隔离 |
| 协议编解码 | `mcp_gateway/protocol.py` | JSON-RPC 请求解析、响应格式化、通知识别 |
| 缓存 | `performance/cache.py` | 缓存命中/未命中、参数差异化识别、统计 |
| 并行调度 | `performance/parallel.py` | DAG 依赖图构建、拓扑排序 |
| 状态管理 | `agent_scheduler/state.py` | 状态创建/消息/错误、序列化、快照管理 |
| 安全检查 | `mcp_gateway/security.py` | 熔断器、权限拦截 |
| 管道验证 | `agent_scheduler/pipeline.py` | 验证器、规划器(基础) |

运行测试：

```bash
# 全部测试 + 覆盖率（推荐）
pytest

# 仅跑单元测试（跳过异步）
pytest -k "not asyncio"

# 生成 HTML 覆盖率报告
pytest --cov-report=html
# 打开 htmlcov/index.html 浏览
```

> **CI 说明**：GitHub Actions 在每次 push 自动执行 `pytest --cov=. --cov-report=xml --cov-report=term-missing`，结果上传 Codecov。
>
> **本地环境**：`pip install pytest-cov` 后即可使用 `--cov` 参数，无需额外配置。

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

### 模块职责 & 状态

| 模块 | 职责 | 状态 | 依赖性 |
|------|------|------|--------|
| `mcp_gateway/` | MCP 协议网关（工具注册、调用、JSON-RPC） | **✅ 核心**，已实现 | 无额外依赖 |
| `performance/` | 缓存、并行调度、模型适配 | **✅ 核心**，已实现 | 无额外依赖 |
| `agent_scheduler/` | LangGraph Agent 调度（Supervisor-Worker） | **✅ 核心**，已实现 | 可选，需 `pip install langgraph` |
| `vllm_adapter/` | vLLM 推理服务进程管理 | **🚧 待扩展** | 可选，需 `vllm` |
| `rag/` | ChromaDB 知识库检索 | **🚧 待扩展** | 可选，需 `chromadb` |

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

## 运维指南

### 动态限流配置

限流器运行时可通过 API 动态调整，无需重启服务：

```bash
# 查看当前限流状态
curl http://localhost:9090/health | jq .rate_limiter

# 调整限流参数（实时生效，写入 config.yaml 可持久化）
#   config.yaml 中的 security.rate_limit 控制全局速率
#   默认: 60 请求/分钟, burst=10
```

| 场景 | 建议值 | 说明 |
|------|--------|------|
| 个人开发机 | 60 req/min | 单用户手动测试 |
| CI 集成 | 120 req/min | 自动化流水线调用 |
| 生产内网 | 300 req/min | 多 Agent 并发接入 |

### 权限配置（白名单模式）

推荐生产环境启用终端白名单，仅允许预设的安全命令：

```python
# mcp_gateway/tools/terminal.py
USE_COMMAND_WHITELIST = True       # 开启白名单模式
ALLOWED_COMMANDS_PREFIXES = [
    "ls", "cat ", "git status",
    "pwd", "find ", "grep ",
    "head ", "tail ", "wc ",
    "echo ", "date", "whoami",
    "pip list", "python --version",
    # 按需添加
]
```

文件系统路径隔离（`SAFE_ROOTS`）默认允许项目目录和用户目录，可通过修改 `mcp_gateway/tools/filesystem.py` 中的常量调整。

### API Key 管理

```bash
# config.yaml 配置预共享密钥
security:
  api_keys:
    - "sk-prod-xxxxxx"
    - "sk-dev-xxxxxx"

# 调用时携带密钥
curl -X POST http://localhost:9090/mcp \
  -H "X-API-Key: sk-prod-xxxxxx" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"tools/list","params":{}}'
```

密钥以 SHA-256 哈希存储于内存，不落盘不暴露。

### 常见故障排查

| 现象 | 可能原因 | 解决 |
|------|----------|------|
| `Connection refused` | 服务未启动或端口冲突 | `python main.py --port 9090` 确认端口未被占用 |
| `Tool not found` | 工具未注册 | `curl POST /mcp -d '{"jsonrpc":"2.0","id":"1","method":"tools/list"}'` 查看可用工具列表 |
| `Access denied: path outside safe roots` | 文件路径不在白名单 | 检查文件路径是否在 `SAFE_ROOTS` 内（见 filesystem.py） |
| `Rate limit exceeded` | 请求频率过高 | 等待 1 分钟后重试，或调大 `rate_limit` 配置 |
| `Command blocked` | 终端黑名单拦截 | 改用白名单模式，将所需命令加入 `ALLOWED_COMMANDS_PREFIXES` |
| 异步测试全部 SKIP | 缺少 pytest-asyncio | `pip install pytest-asyncio` |
| `ModuleNotFoundError: langgraph` | 可选依赖未安装 | `pip install langgraph`（仅 agent_scheduler 需要） |

### 审计日志

安全中间件输出结构化 JSON 日志，可通过环境变量控制日志级别：

```bash
LOG_LEVEL=DEBUG python main.py  # 完整审计日志
LOG_LEVEL=INFO python main.py   # 常规运行日志（默认）
LOG_LEVEL=WARNING python main.py # 仅错误和告警
```

日志格式示例：
```
{"time":"2026-06-25T10:30:00","level":"INFO","module":"mcp_gateway.security",
 "event":"tool_call","tool":"run_command","client":"api_key_a1b2c3d4",
 "result":"SUCCESS","duration_ms":45}
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

核心依赖无版本上界锁定，按最小兼容版本安装：

```txt
# 核心（必需，无附加依赖）
mcp>=1.0.0      # MCP 协议
fastapi>=0.100.0  # HTTP 框架
uvicorn>=0.24.0   # ASGI 服务器
pydantic>=2.5.0  # 数据校验

# Agent 调度（可选）
langgraph>=0.1.0  # 依赖 langchain-core

# RAG（可选，按需安装）
# chromadb>=0.5.0

# vLLM 本地推理（可选，体积大，按需安装）
# vllm>=0.6.0
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