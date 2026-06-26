<p align="center">
  <h1 align="center">MCP Agent Gateway</h1>
  <p align="center">
    <b>让 AI Agent 直接操控本地环境的 MCP 网关</b>
  </p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-blue?style=flat-square&logo=python">
  <img src="https://img.shields.io/badge/version-v3.0-brightgreen?style=flat-square">
  <img src="https://img.shields.io/badge/MCP-2024--11--05-green?style=flat-square">
  <img src="https://img.shields.io/badge/LangGraph-compatible-orange?style=flat-square">
  <img src="https://img.shields.io/badge/tests-105%20passing-brightgreen?style=flat-square">
  <img src="https://img.shields.io/badge/coverage-85%25%2B%20(target)-yellow?style=flat-square">
  <img src="https://img.shields.io/badge/docs-完整-brightgreen?style=flat-square">
  <img src="https://img.shields.io/badge/license-MIT-brightgreen?style=flat-square">
</p>

---

## ⏱️ 30 秒快速启动

```bash
# 克隆
git clone https://github.com/wuwo1979/agent.git && cd agent

# 安装依赖（Python 3.11+）
pip install -r requirements.txt

# 启动 MCP 网关（默认端口 9090）
python main.py --port 9090

# 另开终端验证：列出所有可用工具
curl -X POST http://localhost:9090/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"tools/list","params":{}}'
```

> 无需翻阅任何文档 — 启动后 Trae / Cursor 通过 MCP 配置直接接入，AI Agent 即可调用本地工具。详细的快速开始见下方。

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
│  ┌──────────┐ ┌──────────┐         │
│  │   web    │ │   llm    │         │
│  │ (3 tools)│ │ (2 tools)│         │
│  └──────────┘ └──────────┘         │
│  ┌───────────────────────────────┐  │
│  │ REST API 层：Dify · Trae · Ollama │
│  └───────────────────────────────┘  │
│  ┌───────────────────────────────┐  │
│  │ 性能层：缓存 49.5% · 并行 2.8x │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
        │
        ▼
   本地文件系统 / 终端 / SQLite / Ollama 大模型
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

### 方式 1（推荐）：一键接入任何 IDE

```bash
# 交互式向导 — 自动检测已安装的 IDE，生成配置
python scripts/setup_mcp.py

# 或指定目标 IDE
python scripts/setup_mcp.py --ide trae    # Trae IDE
python scripts/setup_mcp.py --ide cursor  # Cursor IDE
python scripts/setup_mcp.py --ide vscode  # VS Code + Claude Code
python scripts/setup_mcp.py --ide claude  # Claude Desktop
python scripts/setup_mcp.py --ide windsurf # Windsurf (Codeium)

# 同时生成全部 IDE 配置
python scripts/setup_mcp.py --ide all

# 仅查看 JSON 片段（不写入文件）
python scripts/setup_mcp.py --ide trae --json-only

# 测试 MCP 连通性
python scripts/setup_mcp.py --test
```

向导会自动：
1. 检测系统中已安装的 IDE
2. 询问连接模式（HTTP / STDIO）
3. 生成正确的 MCP JSON 配置
4. 写入对应 IDE 的配置文件
5. 测试连通性，列出可用工具

> 支持 **Trae** / **Cursor** / **VS Code** / **Claude Desktop** / **Windsurf** 五大 IDE 的 MCP 配置自动写入。

### 方式 2：手动配置 Trae / Cursor

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

### 方式 3：任何 MCP 客户端

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

## 16 个内置工具

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
| **web** (3) | `web_fetch` | 抓取网页纯文本（自动去 HTML 标签） | 仅 HTTP/HTTPS，15s 超时 |
| | `web_api` | 调用 REST API（GET/POST） | 同上 |
| | `json_query` | JSON 查询（类 jq 路径语法） | 纯内存操作，无副作用 |
| **llm** (2) | `llm_call` | 调用本地 Ollama 大模型生成文本 | 需本地 Ollama 运行中 |
| | `llm_list_models` | 列出已安装的 Ollama 模型 | 只读 |

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
{"jsonrpc":"2.0","id":"1","result":{"protocolVersion":"2024-11-05","serverInfo":{"name":"mcp-gateway","version":"3.0"},"capabilities":{"tools":{},"resources":{},"prompts":{}}}}

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

## REST API（Dify / Trae / Ollama 通用）

除了 MCP JSON-RPC 协议，网关还提供标准 REST API，方便任何 HTTP 客户端直接调用。

### 端点总览

| 端点 | 方法 | 描述 | 认证 |
|------|------|------|------|
| `/api/v1/tools/list` | GET/POST | 列出所有工具（Dify 兼容格式） | 可选（X-API-Key） |
| `/api/v1/tools/call` | POST | 调用指定工具 | 需 API Key |
| `/api/v1/health` | GET | 健康检查 + 组件状态 | 无需认证 |
| `/api/v1/logs` | GET | 审计日志查询（支持过滤） | 无需认证 |
| `/api/v1/stats` | GET | 调用统计（按平台/工具） | 无需认证 |
| `/api/v1/tenants` | GET | 多租户列表（含权限配置） | 无需认证 |

### 工具列表

```bash
curl -X POST http://localhost:9090/api/v1/tools/list \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key"

# 返回 Dify 兼容格式
# {"tools": [{"name": "sysinfo", "description": "...", "parameters": [...]}, ...], "count": 16}
```

### 工具调用

```bash
curl -X POST http://localhost:9090/api/v1/tools/call \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"name": "sysinfo", "arguments": {}}'

# 返回
# {"success": true, "tool_name": "sysinfo", "result": "{...}", "duration_ms": 12.5}
```

### 审计日志

```bash
# 查询所有日志
curl http://localhost:9090/api/v1/logs

# 按平台过滤
curl "http://localhost:9090/api/v1/logs?platform=dify&limit=20"

# 按工具过滤
curl "http://localhost:9090/api/v1/logs?tool=sysinfo"

# 仅查看错误
curl "http://localhost:9090/api/v1/logs?error_only=true"
```

---

## 平台对接指南

### Dify 自定义工具网关

1. 启动网关：`python main.py --port 9090`
2. 在 Dify 工作流中添加「自定义工具」节点
3. 配置 API 端点：
   - 工具列表：`POST http://localhost:9090/api/v1/tools/list`
   - 工具调用：`POST http://localhost:9090/api/v1/tools/call`
4. 在 Header 中添加 `X-API-Key: your-key`
5. Dify 将自动发现 16 个工具，可在工作流中拖拽使用

> Dify 调用会自动记录到审计日志，可通过 `/api/v1/logs?platform=dify` 查看。

### Ollama 本地大模型工具中台

```bash
# 前提：确保 Ollama 已安装并运行
ollama serve

# 下载模型（如未安装）
ollama pull qwen2.5:7b

# 启动网关后，Agent 即可调用 llm_call / llm_list_models 工具
python main.py --port 9090
```

通过网关，AI Agent 可以：
- `llm_call`：调用本地模型生成文本（无需 API Key，完全离线）
- `llm_list_models`：查看已安装模型列表

```bash
# 测试 LLM 调用
curl -X POST http://localhost:9090/api/v1/tools/call \
  -H "Content-Type: application/json" \
  -d '{"name": "llm_call", "arguments": {"model": "qwen2.5:7b", "prompt": "解释什么是 MCP 协议"}}'
```

### Trae MCP 代理层

```bash
# 一键配置
python scripts/setup_mcp.py --ide trae
```

Trae 通过 MCP 协议直接接入网关，可调用全部 16 个工具。详见上方「集成方式」章节。

### 多租户权限隔离

每个 API Key 绑定一个租户 (Tenant)，拥有独立的文件白名单和工具策略。

```bash
# 查看所有租户
curl http://localhost:9090/api/v1/tenants

# 返回示例
# {
#   "tenants": [
#     {"tenant_id": "admin", "label": "管理员", "allowed_tools": []},
#     {"tenant_id": "dify_default", "label": "Dify默认租户", "allowed_tools": ["sysinfo", "read_file", ...]},
#     {"tenant_id": "ollama_local", "label": "Ollama本地工具", "allowed_tools": ["llm_call", "llm_list_models", ...]}
#   ]
# }
```

**默认租户即开即用**：admin（全部权限）、dify_default（文件/Web 工具）、ollama_local（LLM 工具）。

```python
# 自定义租户（代码中添加）
from mcp_gateway.tenancy import get_tenancy

tenancy = get_tenancy()
tenancy.add_tenant(
    tenant_id="my_app",
    api_keys=["my-app-key"],
    file_whitelist=["/project/myapp/"],
    allowed_tools={"sysinfo", "read_file", "list_dir", "web_fetch"},
)
```

---

## 性能指标

> ### 🔍 统一前置约束
>
> | 约束项 | 说明 |
> |--------|------|
> | **测试硬件** | Windows 11 专业版, Intel i7-12700 (12 核 20 线程), DDR4 32GB |
> | **Python 版本** | 3.11.5 (CPython) |
> | **测试工具** | Mock Provider（纯内存，零 I/O 抖动） |
> | **对比基线** | 无缓存 + 串行 `await` 逐个执行 |
> | **数据来源** | `python tests/generate_charts.py`（自动生成，可复现） |
> | **适用边界** | 并行加速比仅适用于 **无依赖的独立任务**；缓存率依赖调用模式（见下） |
>
> 以下所有数据均在上述环境中实测取得。若在生产环境（不同硬件、网络延迟、并发负载），绝对数值会变化，但**相对提升趋势**保持有效。

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

| 维度 | 基准方案 | MCP Gateway | 提升幅度 | 适用场景 |
|------|----------|-------------|----------|----------|
| 多工具调用 | 串行 749.0ms | 并行 264.7ms | [加速] **2.8x** | **仅无依赖的独立任务**（如同时读多个文件） |
| 重复上下文 | 完整体积 100% 传输 | 增量缓存命中 43% | [节省] **50%** Token | 同一 Agent 多次调用含重复参数 |
| DAG 依赖调度 | 全串行 4 节点 | 分 3 级并行 | [加速] **约 45%** 耗时缩减 | 有拓扑依赖的多步骤工作流 |

### 详细指标

| 指标 | 实测值 | 对比基准 | 适用边界 | 说明 |
|------|--------|----------|----------|------|
| Token 压缩率 | **50%** | 无缓存全量回传 | 8 次调用含 3 次重复参数 | 增量缓存：重复的工具调用只传增量 |
| 并行加速比 | **2.8x** | 串行逐个执行 | **仅无依赖任务**。6 个独立工具混合耗时 | asyncio.gather vs await 串行 |
| 延迟降低 | **64.4%** | 串行基线 | 同上 | (1 - 并行/串行) × 100% |
| **缓存命中率(全局)** **¹** | **43%** | 全局统计 | 首次 8 次调用含 5 MISS + 3 HIT | 含首次冷启动，反映真实首次接入表现 |
| **缓存命中率(热)** **²** | **66.7%** | 重复调用 | 同一操作连续 3 轮 | 排除冷启动，反映长对话/重复任务场景 |

> **¹ 全局命中率**：从空缓存开始，首次 8 次调用中 5 次 MISS（冷启动）+ 3 次 HIT，整体命中 3/8 = 43%。适用于**首次接入**场景。  
> **² 热命中率**：排除首次冷启动后，后续重复调用命中 2/3 ≈ 66.7%。适用于**长对话持续交互**场景，更贴近实际连续使用表现。  
> **关于并行加速比的边界**：2.8x 加速比仅适用于**无依赖的独立任务并行执行**。对于存在强串行依赖的 DAG 任务（如 A→B→C 必须顺序执行），加速效果受拓扑分层限制，无法达到此值。benchmark 使用 6 个完全独立的工具以显示最大理论加速效果。

---

## 测试覆盖

> 当前 **105 个测试用例**（17 个 MCP 核心 + 17 个 Agent 调度 + 71 个集成测试）。覆盖安全、多租户、API、审计、边界条件、异常路径。

### 测试分类

| 测试文件 | 用例数 | 覆盖范围 |
|----------|--------|----------|
| `tests/test_mcp.py` | 17 | 工具注册、协议编解码、MCP 协议处理 |
| `tests/test_agent.py` | 17 | Agent 状态、重试/熔断、缓存、并行调度 |
| `tests/test_integration.py` | 71 | 安全认证、速率限制、多租户、API 接口、审计日志、边界条件、异常路径、性能基准 |

### 核心模块覆盖

| 模块 | 覆盖内容 |
|------|----------|
| `mcp_gateway/security.py` | API Key 认证、令牌桶限流、工具权限策略、安全中间件 |
| `mcp_gateway/tenancy.py` | 租户注册/移除、API Key 分组、文件白名单、工具权限隔离 |
| `mcp_gateway/audit.py` | 审计日志记录、环形缓冲区、多维度查询、统计 |
| `mcp_gateway/api.py` | Dify 兼容 REST API、工具列表/调用、健康检查 |
| `mcp_gateway/protocol.py` | JSON-RPC 解析/响应、工具注册/调用 |
| `performance/cache.py` | LRU 缓存命中/未命中、内容去重 |
| `performance/parallel.py` | 依赖图构建、拓扑排序、并行执行 |

运行测试：

```bash
# 全部测试
pytest

# 特定模块
pytest tests/test_integration.py -v

# 生成 HTML 覆盖率报告
pytest --cov=. --cov-report=html
```

---

## 安全设计

### 多层安全防护

| 层级 | 模块 | 措施 |
|------|------|------|
| **认证** | `security.py` | API Key 验证（X-API-Key header），SHA-256 哈希存储 |
| **限流** | `security.py` | 令牌桶算法，60 req/min，burst=10 |
| **权限** | `security.py` | 工具权限策略引擎，危险工具拦截，只读工具放行 |
| **多租户** | `tenancy.py` | API Key 分组隔离，独立文件白名单，工具权限控制 |
| **审计** | `audit.py` | 环形缓冲区日志，多维度查询（平台/工具/调用方/结果） |
| **终端** | `tools/terminal.py` | 23 条破坏性命令黑名单 + 交互命令拦截 + 可选白名单模式 |
| **文件系统** | `tools/filesystem.py` | 路径隔离（SAFE_ROOTS）+ 路径穿越防护 |

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
| `mcp_gateway/` | MCP 协议网关（工具注册、调用、JSON-RPC、安全、多租户、审计、REST API） | **✅ 核心** | 无额外依赖 |
| `performance/` | 缓存、并行调度、模型适配 | **✅ 核心** | 无额外依赖 |
| `agent_scheduler/` | LangGraph Agent 调度（Supervisor-Worker） | **✅ 核心**，已实现 | 可选，需 `pip install langgraph` |
| `vllm_adapter/` | vLLM 推理服务进程管理 | **🚧 待扩展** | 可选，需 `vllm` |
| `rag/` | ChromaDB 知识库检索 | **🚧 待扩展** | 可选，需 `chromadb` |

### 目录结构

```
agent/
├── ✅ mcp_gateway/          # 【核心】MCP 协议网关
│   ├── protocol.py          # JSON-RPC + 工具注册
│   ├── transport.py         # HTTP/SSE 传输
│   ├── server.py            # 生产级入口
│   ├── security.py          # 认证 + 限流 + 权限
│   └── tools/               # 14 个内置工具
├── ✅ performance/          # 【核心】性能优化
│   ├── cache.py             # 增量上下文缓存
│   ├── parallel.py          # 并行调度 + 拓扑排序
│   └── adapter.py           # 多模型适配
├── ✅ agent_scheduler/      # 【核心】Agent 调度（需 pip install langgraph）
│   ├── graph.py             # LangGraph 工作流
│   ├── supervisor.py        # Supervisor-Worker
│   ├── state.py             # 状态 + 文件快照
│   └── agents/              # Planner + Executor + Validator
├── 🚧 vllm_adapter/         # 【待扩展】vLLM 推理管理（需 vllm）
├── 🚧 rag/                  # 【待扩展】知识库检索（需 chromadb）
├── core/                    # 基础设施（类型、异常、接口）
├── config/                  # 配置加载
├── tests/                   # 测试 + 跑分
│   ├── test_mcp.py          # MCP 核心单元测试（17 个用例）
│   ├── test_agent.py        # Agent 调度测试（17 个用例）
│   ├── test_integration.py  # 集成测试（71 个用例）
│   ├── benchmark.py         # 5 项性能跑分（含环境信息）
│   └── generate_charts.py   # 基准数据自动生成
├── examples/                # 集成示例
│   └── integration_demo.py
├── scripts/                 # 工具脚本
│   ├── setup_mcp.py         # 一键接入 IDE 配置向导
│   └── build_exe.py         # PyInstaller 打包
├── docker/                  # Docker 部署
├── docs/                    # 技术文档
│   ├── 面试问答.md           # 技术决策深度问答（自研 vs LangGraph/LangChain）
│   ├── 架构设计.md           # 分层架构设计、多平台接入方案
│   └── 设计决策.md           # 架构决策记录（ADR）
├── demo.py                  # 演示脚本
└── main.py                  # 主入口
```

> **图例**：✅ = 已实现核心模块 / 🚧 = 待扩展规划模块（预留目录、无完整业务代码）

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

## 技术文档

详细技术文档见 `docs/` 目录：

| 文档 | 内容 |
|------|------|
| [面试问答](docs/面试问答.md) | 技术决策深度问答：为什么自研多 Agent 调度而非 LangGraph？为什么自写 LRU 缓存而非 LangChain Memory？AI Infra 架构定位 |
| [架构设计](docs/架构设计.md) | 分层架构图、核心模块职责、Dify/Trae/Ollama 多平台接入方案、安全与性能优化设计 |
| [设计决策](docs/设计决策.md) | 架构决策记录（ADR）：JSON-RPC 2.0 协议选型、Agent 自研方案、缓存策略、HTTP 框架选型 |

---

## License

MIT