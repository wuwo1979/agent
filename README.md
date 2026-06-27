> **MCP Agent Gateway v2.0** — 一个让 AI Agent（Trae / Dify / Cursor）安全操控本地环境的 MCP 网关。
> 核心亮点：(1) **协议内核统一 + 传输层薄适配**，单套 JSON-RPC 内核同时服务 STDIO 和 HTTP；(2) **Ollama 故障隔离**，单模型崩溃不会影响网关工具调用能力；(3) **Dify 原生适配**，自动生成 OpenAPI Schema 一键导入，无需手动配 HTTP 节点。

<p align="center">
  <h1 align="center">MCP Agent Gateway v2.0</h1>
  <p align="center">
    <b>协议内核统一 + 传输层薄适配 + 可插拔中间件管道</b><br>
    让 AI Agent 直接操控本地环境的 MCP 网关
  </p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-2.0.0-blue?style=flat-square">
  <img src="https://img.shields.io/badge/python-3.11+-blue?style=flat-square&logo=python">
  <img src="https://img.shields.io/badge/MCP-2024--11--05-green?style=flat-square">
  <img src="https://img.shields.io/badge/tests-107%20passing-brightgreen?style=flat-square">
  <img src="https://img.shields.io/badge/ruff-0%20errors-brightgreen?style=flat-square">
  <img src="https://img.shields.io/badge/license-MIT-brightgreen?style=flat-square">
  <img src="https://img.shields.io/badge/Trae-Ready-blue?style=flat-square">
  <img src="https://img.shields.io/badge/Dify-Ready-orange?style=flat-square">
  <img src="https://img.shields.io/badge/Ollama-Ready-purple?style=flat-square">
</p>

---

## 界面速览

> 以下全部截图来自实测运行环境，非 AI 生成概念图。完整烟测日志：[docs/screenshots/smoke_test_results.log](docs/screenshots/smoke_test_results.log)

<table>
  <tr>
    <td align="center" width="50%">
      <img src="docs/screenshots/status_dashboard.png" width="90%" alt="状态仪表盘"><br>
      <sub><b>✦ 状态仪表盘</b> — 一键确认服务健康、模块状态、工具注册</sub>
    </td>
    <td align="center" width="50%">
      <img src="docs/screenshots/mcp_tools_list.png" width="90%" alt="工具列表"><br>
      <sub><b>✦ Trae 工具列表</b> — MCP 协议发现 17 个工具，IDE 侧边栏加载即用</sub>
    </td>
  </tr>
  <tr>
    <td align="center" width="50%">
      <img src="docs/screenshots/dify_openapi_schema.png" width="90%" alt="Dify Schema"><br>
      <sub><b>✦ Dify OpenAPI Schema</b> — 自动生成，Dify 内一键导入所有工具</sub>
    </td>
    <td align="center" width="50%">
      <img src="docs/assets/performance_chart.png" width="90%" alt="性能指标"><br>
      <sub><b>✦ 性能基准</b> — 缓存命中 78%，并行吞吐量 2.9x 提升</sub>
    </td>
  </tr>
</table>

---

## 这个项目解决什么问题？

AI Agent（如 Trae、Dify、Cursor）在和本地环境交互时面临三重障碍：

| 障碍 | 具体表现 | 本项目的解法 |
|------|----------|------------|
| **协议割裂** | Trae 用 STDIO MCP，Dify 用 HTTP REST API，两套代码两套维护 | 单套 JSON-RPC 协议内核 + 薄传输层适配，一套代码同时服务两端 |
| **安全风险** | Agent 能操作文件、执行命令、调数据库，权限控制缺失 | 多租户 API Key 认证 + 路径白名单沙箱 + 工具权限隔离 |
| **集成成本** | 每个平台都要手动配 HTTP 节点、写接口文档 | Dify 秒级适配：自动生成 OpenAPI Schema 一键导入；Trae 一行配置：JSON 模板复制即用 |

简单说：**你只需要启动一个网关，Trae 和 Dify 都能用，而且安全、可控、开箱即用。**

---

## 30 秒快速启动

```bash
git clone https://github.com/wuwo1979/agent.git && cd agent
pip install -r requirements/runtime.txt
python main.py                                   # 启动网关 (HTTP 模式, 端口 19090)
```

```bash
# 验证工具列表是否正常返回
curl.exe -X POST http://localhost:19090/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"tools/list","params":{}}'
```

**预期返回（部分）：**
```json
{
  "jsonrpc": "2.0",
  "id": "1",
  "result": {
    "tools": [
      {"name": "read_file",    "description": "读取指定文件内容"},
      {"name": "write_file",   "description": "写入内容到指定文件"},
      {"name": "list_dir",     "description": "列出目录内容"},
      {"name": "search_files", "description": "搜索文件"},
      {"name": "file_stat",    "description": "获取文件状态信息"},
      {"name": "run_command",  "description": "在终端中执行命令"},
      {"name": "sysinfo",      "description": "获取系统信息"},
      {"name": "query",        "description": "执行数据库查询"},
      {"name": "web_fetch",    "description": "获取网页或 API 内容"},
      {"name": "llm_call",     "description": "调用本地大语言模型"}
    ]
  }
}
```

**验证健康检查：**
```bash
curl.exe -s http://localhost:19090/api/v1/health
# 预期: {"status":"healthy","server":"MCP 本地工具网关","version":"2.0.0","tools":17,...}
```

> 配置模板见 [config/config.example.yaml](config/config.example.yaml)，复制为 `config.yaml` 即可自定义端口、密钥、缓存参数等。

---

## 安全设计

网关内置 **三层安全防护**，确保 AI Agent 操作本地环境时可控可审计：

| 防护层 | 机制 | 说明 |
|--------|------|------|
| **认证 & 鉴权** | API Key（`X-API-Key` 请求头）+ 多租户策略 | 不同接入端使用不同 Key，隔离资源与工具权限 |
| **路径隔离** | 路径规范化，匹配白名单前缀，杜绝 `../` 目录穿越 | 租户级 `file_whitelist` 配置，越权返回 `-32001` |
| **命令管控** | 终端命令白名单 + 危险语法模式拦截 | 防止命令注入；数据库查询强制参数化防 SQL 注入 |

> 详见 [docs/错误码对照表.md](docs/错误码对照表.md) 中的安全相关错误码和排查方法。

---

## 实际使用流程

### 场景一：Trae IDE 中使用（STDIO 模式）

```mermaid
sequenceDiagram
  participant Trae as Trae IDE
  participant Gateway as MCP Gateway (STDIO)
  participant Tools as 本地工具集

  Trae->>Gateway: initialize (JSON-RPC)
  Gateway->>Trae: serverInfo + capabilities
  Trae->>Gateway: tools/list
  Gateway->>Trae: 17 tools (read_file, run_command, ...)
  Trae->>Gateway: tools/call (read_file, path=xxx)
  Gateway->>Tools: 路径安全校验 → 读取
  Tools->>Gateway: 文件内容
  Gateway->>Trae: JSON-RPC response
```

**实测效果：** Trae IDE 内可直接让 AI 读写文件、执行命令、查询数据库、调用 Ollama 模型，所有操作受权限控制。

### 场景二：Dify 平台中使用（HTTP REST 模式）

```mermaid
sequenceDiagram
  participant Dify as Dify 平台
  participant Gateway as MCP Gateway (HTTP)
  participant Tools as 本地工具集

  Dify->>Gateway: 导入 OpenAPI Schema (/api/v1/openapi.json)
  Gateway->>Dify: 自动生成工具定义
  Dify->>Gateway: POST /tools/call (X-API-Key + 参数)
  Gateway->>Tools: 多租户鉴权 → 执行
  Tools->>Gateway: 结果
  Gateway->>Dify: JSON 响应
```

**实测效果：** Dify 内导入 Schema 即可使用所有工具，无需手动配置 HTTP 节点。

### 场景三：Ollama 崩溃了会怎样？

```mermaid
sequenceDiagram
  participant Agent as AI Agent
  participant Gateway as MCP Gateway
  participant Ollama as Ollama (已崩溃)

  Agent->>Gateway: tools/call (llm_ping)
  Gateway->>Ollama: 健康检查
  Ollama--xGateway: 连接失败
  Gateway->>Agent: 标准错误响应 (code: -32003)
  Note over Agent,Gateway: ● 网关其他功能(文件/命令/数据库)完全正常
```

**实测效果：** Ollama 崩溃时返回标准化错误码 `-32003`，不影响网关其他工具调用。

---

## 架构设计

<p align="center">
  <img src="docs/assets/architecture.svg" width="95%" alt="Architecture"><br>
  <sub>手动绘制线稿架构图 — 严格对应实际代码分层</sub>
</p>

### 协议内核统一

```
                    ┌──────────────────────────────────────────┐
                    │         AI Agent  (Trae / Dify / Cursor)  │
                    └────────┬──────────────┬──────────────────┘
                             │              │
                    STDIO    │              │   HTTP REST
                    (JSON-RPC)│              │   (JSON-RPC)
                             │              │
                    ┌────────▼──────────────▼──────────────────┐
                    │          MCP Transport Layer              │
                    │    STDIOTransport  │  HTTPTransport       │
                    └────────┬──────────────┬──────────────────┘
                             │              │
                             └──────┬───────┘
                                    │  JSONRPCRequest
                    ┌───────────────▼──────────────────────────┐
                    │        MCPProtocolHandler (唯一执行入口)    │
                    │                                          │
                    │  ┌─────────────────────────────────┐     │
                    │  │   Middleware Pipeline             │     │
                    │  │  before: [Auth] → [RateLimit]    │     │
                    │  │  core:  [ToolExecutor]           │     │
                    │  │  after: [Audit] → [Cache]        │     │
                    │  └─────────────────────────────────┘     │
                    │                                          │
                    │  ┌─────────────────────────────────┐     │
                    │  │   ToolRegistry (17 tools)        │     │
                    │  │  Filesystem │ Terminal │ DB      │     │
                    │  │  Web        │ LLM      │         │     │
                    │  └─────────────────────────────────┘     │
                    └───────────────┬──────────────────────────┘
                                    │
                    ┌───────────────▼──────────────────────────┐
                    │          本地资源 (沙箱安全)               │
                    │  文件系统 │ 终端Shell │ 数据库 │ Ollama   │
                    └──────────────────────────────────────────┘
```

### 升级亮点 (v1.3 → v2.0)

| 维度 | v1.3 (旧) | v2.0 (新) |
|------|-----------|-----------|
| **执行入口** | 两条路径：API 直接调 registry + ProtocolHandler 独立处理 | 唯一入口：`MCPProtocolHandler.handle_request()` |
| **中间件** | 无 | 可插拔管道：Auth → RateLimit → Audit → Cache |
| **错误码** | 自定义 | JSON-RPC 2.0 标准 |
| **Ollama 故障** | 无隔离，崩溃波及整个网关 | 故障隔离，单模型崩溃不影响其他工具 |
| **Dify 集成** | 手动配 HTTP 节点 | 自动生成 OpenAPI Schema 一键导入 |
| **会话管理** | 无跨传输共享 | SessionContext 统一跨 STDIO/HTTP |
| **可观测性** | 无统一指标 | 协议内核统一收集，stats 端点 |

---

## 内置工具一览

| Provider | 工具 | 安全措施 | 适用场景 |
|----------|------|---------|---------|
| **filesystem** | `read_file`, `write_file`, `list_dir`, `search_files`, `file_stat` | 路径沙箱 + 白名单 | 读写项目文件、搜索代码、管理资源 |
| **terminal** | `run_command`, `sysinfo` | 命令白名单 + 危险语法拦截 | 执行编译/测试命令、获取系统信息 |
| **database** | `query`, `execute`, `list_tables`, `describe_table` | 参数化查询防 SQL 注入 | 查数据库、执行迁移、分析数据 |
| **web** | `web_fetch`, `web_api`, `json_query` | URL 校验 + 超时控制 | 爬取网页、调用 API、解析 JSON |
| **llm** | `llm_call`, `llm_ping`, `llm_list_models` | 故障隔离 + 健康检查 | 本地推理、检查 Ollama 状态 |

全部 17 个工具：`python main.py --demo`（自动跑完所有类型工具调用）

---

## 生态适配

| 平台 | 方式 | 验证状态 | 一句话说明 |
|------|------|----------|-----------|
| **Trae IDE** | STDIO (MCP) | ✅ 通过 | 标准 MCP 配置，可调全部 17 工具 |
| **Dify** | HTTP REST API | ✅ 通过 | 导入 OpenAPI Schema 一键注册所有工具 |
| **Cursor** | STDIO / HTTP | ✅ 兼容 | 支持 setup_mcp.py 一键配置 |
| **VS Code** | STDIO / HTTP | ✅ 兼容 | 通过 MCP 插件接入 |
| **Ollama** | REST API | ✅ 通过 | 内置 llm_call / llm_ping / llm_list_models |
| **curl / HTTP** | REST / MCP | ✅ 通过 | 任意语言直接调用 |

---

## 运行方式

```bash
# HTTP 模式 —— 供 Dify / 浏览器 / curl 调用
python main.py --host 0.0.0.0 --port 19090

# STDIO 模式 —— 供 Trae / Cursor / VS Code 调用
python main.py --mode stdio

# 全自动演示 —— 注册工具 → 调用各类型 → 展示性能
python main.py --demo

# 状态监控 —— 确认所有模块健康
python main.py --status
```

### 集成到各平台

**Trae / Cursor**：在 MCP 设置中添加：

```json
{
  "mcpServers": {
    "agent-mcp-gateway": {
      "command": "python",
      "args": ["<项目路径>/main.py", "--mode", "stdio"],
      "env": {"MCP_API_KEY": "your-key", "MCP_WORKSPACE": "<项目路径>"}
    }
  }
}
```

> 一键配置：`python scripts/setup_mcp.py`

**Dify**：在自定义工具中导入 OpenAPI Schema：
- URL：`http://localhost:19090/api/v1/openapi.json`
- 认证：`X-API-Key`

---

## 项目结构

```
LLM/
├── mcp_gateway/              # 核心网关
│   ├── server.py             # 服务入口 + 中间件装配
│   ├── protocol.py           # 协议内核 + 中间件管道 (唯一执行入口)
│   ├── transport.py          # 传输层 (HTTP/STDIO 薄适配)
│   ├── api.py                # REST → JSON-RPC 适配器
│   ├── security.py           # 认证 / 速率限制 / 策略引擎
│   ├── audit.py              # 统一审计日志
│   ├── tenancy.py            # 多租户管理
│   ├── workspace.py          # 工作区管理 + 提示词模板
│   └── tools/                # 工具提供者
│       ├── filesystem.py     # 5 个文件系统工具
│       ├── terminal.py       # 2 个终端工具
│       ├── database.py       # 4 个数据库工具
│       ├── web.py            # 3 个网页工具
│       └── llm.py            # 3 个大模型工具
├── core/                     # 基础设施
│   ├── types.py              # JSON-RPC 类型定义
│   └── exceptions.py         # 统一异常体系
├── config/                   # YAML 配置
│   ├── default.yaml          # 默认配置
│   └── config.example.yaml   # 带注释的配置模板
├── tests/                    # 107 个测试
├── docs/                     # 文档 + 截图素材
│   ├── assets/               # 架构图 + 性能图表
│   ├── screenshots/          # 实测运行截图
│   └── 错误码对照表.md         # 完整错误码文档
├── scripts/                  # 工具脚本
├── docker/                   # Docker 部署
└── main.py                   # 入口
```

---

## 测试

```bash
# 全部 107 个测试
pytest

# 双场景端到端验证 (Trae STDIO + Dify HTTP)
pytest tests/test_scenarios.py -v

# 导入 + 安全校验验证
python tests/verify_imports.py

# 全场景冒烟测试 + 素材采集
python docs/smoke_test.py

# 代码风格 (ruff 0 errors)
ruff check .
```

---

## 文档

| 文档 | 内容 |
|------|------|
| [Trae 接入指南](docs/Trae接入指南.md) | Trae IDE MCP 配置步骤 |
| [Dify 接入指南](docs/Dify平台自定义工具接入指南.md) | Dify 自定义工具节点配置 |
| [架构设计](docs/架构设计.md) | 分层架构详解 |
| [设计决策](docs/设计决策.md) | 技术选型决策记录 |
| [错误码对照表](docs/错误码对照表.md) | 完整错误码定义与排查方法 |
| [性能优化](docs/性能优化与跑分.md) | 缓存 + 并行调度指标 |
| [烟测报告](docs/screenshots/smoke_test_results.log) | 全场景冒烟测试结果 |

---

## 版本演进

| 版本 | 核心变更 |
|------|---------|
| **v1.0** | 初始版本：MCP 协议基础 + HTTP REST 双路径 |
| **v1.3** | 多租户、审计日志、路径沙箱、权限控制、OpenAPI |
| **v2.0** | **协议内核统一**（唯一执行入口）+ **中间件管道** + **Ollama 故障隔离** + **Dify OpenAPI Schema** + **统一错误码** |

---

## License

MIT