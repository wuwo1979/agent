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
  <img src="https://img.shields.io/badge/tests-108%20passing-brightgreen?style=flat-square">
  <img src="https://img.shields.io/badge/ruff-0%20errors-brightgreen?style=flat-square">
  <img src="https://img.shields.io/badge/license-MIT-brightgreen?style=flat-square">
  <img src="https://img.shields.io/badge/Trae-Ready-blue?style=flat-square">
  <img src="https://img.shields.io/badge/Dify-Ready-orange?style=flat-square">
  <img src="https://img.shields.io/badge/Ollama-Ready-purple?style=flat-square">
</p>

---

## 30 秒快速启动

```bash
git clone https://github.com/wuwo1979/agent.git && cd agent
pip install -r requirements/runtime.txt
python main.py                                   # 启动网关 (HTTP 模式, 端口 9090)
```

```bash
# 验证
curl -X POST http://localhost:9090/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"tools/list","params":{}}'
```

---

## v2.0 架构升级概览

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
                    │    (readline逐行)  │  (aiohttp SSE)      │
                    └────────┬──────────────┬──────────────────┘
                             │              │
                             └──────┬───────┘
                                    │  JSONRPCRequest
                    ┌───────────────▼──────────────────────────┐
                    │        MCPProtocolHandler (唯一入口)       │
                    │                                          │
                    │  ┌─────────────────────────────────┐     │
                    │  │   Middleware Pipeline (中间件管道) │     │
                    │  │                                  │     │
                    │  │  before: [Auth] → [RateLimit]    │     │
                    │  │     ↓                            │     │
                    │  │  core:  [ToolExecutor]           │     │
                    │  │     ↓                            │     │
                    │  │  after: [Audit] → [Cache]        │     │
                    │  └─────────────────────────────────┘     │
                    │                                          │
                    │  ┌─────────────────────────────────┐     │
                    │  │       ToolRegistry (统一注册表)    │     │
                    │  │  Filesystem │ Terminal │ DB      │     │
                    │  │  Web        │ LLM      │ ...     │     │
                    │  └─────────────────────────────────┘     │
                    └───────────────┬──────────────────────────┘
                                    │
                    ┌───────────────▼──────────────────────────┐
                    │          本地资源 (沙箱安全)               │
                    │  文件系统 │ 终端Shell │ 数据库 │ Ollama   │
                    └──────────────────────────────────────────┘
```

### v1.3 → v2.0 核心变化

| 维度 | v1.3 (旧) | v2.0 (新) |
|------|-----------|-----------|
| **执行入口** | 两条路径：ExternalAPIHandler 直接调 registry + ProtocolHandler 独立处理 | 唯一入口：`MCPProtocolHandler.handle_request()` |
| **HTTP 层职责** | 混入工具执行逻辑 | 纯适配器：REST → JSON-RPC 转换 |
| **错误码** | 自定义 -32000 | JSON-RPC 2.0 标准 (-32603 等) |
| **中间件** | 无 | 可插拔管道：Auth → RateLimit → Audit → Cache |
| **会话管理** | 无跨传输共享 | SessionContext 统一跨 STDIO/HTTP |
| **可观测性** | 无统一指标 | 协议内核统一收集，stats 端点 |
| **流式输出** | 各传输层自行实现 | 协议内核统一 SSE 流式管道 |

### 进程全景图

```
启动 → python main.py
         │
         ├── HTTP 模式 (--mode http)
         │     │
         │     ├── 监听 0.0.0.0:9090
         │     ├── /mcp          → MCP JSON-RPC 端点
         │     ├── /api/v1/      → REST API (Dify 自定义工具)
         │     ├── /api/v1/health → 健康检查
         │     ├── /api/v1/logs   → 审计日志
         │     └── /api/v1/tenants → 租户管理
         │
         └── STDIO 模式 (--mode stdio)
               │
               ├── stdin  ← 读取 JSON-RPC 请求
               ├── stdout → 输出 JSON-RPC 响应 (纯 JSON，无日志)
               └── stderr → 所有日志/调试输出
```

---

## 生态适配

| 平台 | 方式 | 验证状态 | 说明 |
|------|------|----------|------|
| **Trae IDE** | STDIO (MCP) | ✅ 通过 | 标准 MCP 配置，可调全部 17 工具 |
| **Dify** | HTTP REST API | ✅ 通过 | 自定义工具节点，自动发现工具列表 |
| **Cursor** | STDIO / HTTP (MCP) | ✅ 兼容 | 同上，支持 setup_mcp.py 一键配置 |
| **VS Code** | STDIO / HTTP (MCP) | ✅ 兼容 | 通过 MCP 插件接入 |
| **Ollama** | REST API | ✅ 通过 | 内置 llm_call / llm_ping / llm_list_models |
| **curl / HTTP 客户端** | REST / MCP | ✅ 通过 | 任意语言直接调用 |

### 真实可用性验证

```bash
# 全部场景测试 (Trae STDIO + Dify HTTP)
python -m pytest tests/test_scenarios.py -v

# 结果:
# tests/test_scenarios.py::test_stdio_mode PASSED  [Trae IDE 场景]
# tests/test_scenarios.py::test_http_mode  PASSED  [Dify 平台场景]
# ============================= 108 passed in 3.67s =============================
```

**Trae IDE STDIO 模式验证流程：**
```
1. 启动子进程: python main.py --mode stdio
2. 发送 initialize 请求 → 收到 server_info
3. 发送 tools/list 请求 → 收到 18+ 工具列表
4. 发送 tools/call (echo) → 收到正常响应
5. 发送 tools/call (read_file) → 路径安全校验通过
6. 进程正常退出 ✓
```

**Dify HTTP REST 模式验证流程：**
```
1. 启动 HTTP 服务: python main.py --mode http --port 19090
2. GET /api/v1/health → 200 {"status":"healthy"}
3. POST /api/v1/tools/list → 工具列表 JSON
4. POST /api/v1/tools/call → 工具调用成功
5. GET /api/v1/logs → 审计日志记录完整
6. 服务关闭 ✓
```

---

## 运行方式

```bash
# HTTP 模式 —— 供 Dify / 浏览器 / curl 调用
python main.py --host 0.0.0.0 --port 9090

# STDIO 模式 —— 供 Trae / Cursor / VS Code 调用
python main.py --mode stdio

# 状态监控
python main.py --status

# 演示
python main.py --demo
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

**Dify**：在 HTTP 请求节点配置：
- 工具列表：`POST http://localhost:9090/api/v1/tools/list`
- 工具调用：`POST http://localhost:9090/api/v1/tools/call`

**Ollama**：启动 Ollama 后直接调用 `llm_call` / `llm_ping` / `llm_list_models` 工具

---

## 内置工具

| Provider | 工具 | 说明 |
|----------|------|------|
| **filesystem** | `read_file`, `write_file`, `list_dir`, `search_files`, `file_stat` | 路径隔离沙箱，防目录穿越 |
| **terminal** | `run_command`, `sysinfo` | 命令黑/白名单 + 超时控制 |
| **database** | `query`, `execute`, `list_tables`, `describe_table` | 参数化查询防 SQL 注入 |
| **web** | `web_fetch`, `web_api`, `json_query` | HTTP/HTTPS + 超时 |
| **llm** | `llm_call`, `llm_ping`, `llm_list_models` | Ollama 本地推理 |

全部 17 工具：`python main.py --demo`

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
├── performance/              # 缓存 + 并行调度
├── config/                   # YAML 配置
├── requirements/             # 依赖管理
├── tests/                    # 108 个测试
│   ├── test_scenarios.py     # Trae+Dify 双场景端到端验证
│   ├── test_integration.py   # 集成测试
│   ├── test_mcp.py           # 协议层单元测试
│   └── verify_imports.py     # 导入 + 安全校验验证
├── examples/                 # 集成示例
├── scripts/                  # 工具脚本
├── docker/                   # Docker 部署
├── docs/                     # 文档
└── main.py                   # 入口
```

---

## 测试

```bash
pytest                              # 全部 108 个测试
pytest tests/test_scenarios.py -v   # 双场景验证
python tests/verify_imports.py      # 导入 + 安全校验
ruff check . --select=E,F,W --ignore=E501  # 代码风格
```

---

## 文档

| 文档 | 内容 |
|------|------|
| [Trae 接入指南](docs/Trae接入指南.md) | Trae IDE MCP 配置步骤 + STDIO 配置模板 |
| [Dify 接入指南](docs/Dify平台自定义工具接入指南.md) | Dify 自定义工具节点配置 + 调试步骤 |
| [架构设计](docs/架构设计.md) | 分层架构、多平台接入 |
| [设计决策](docs/设计决策.md) | 技术选型决策记录 |
| [MCP 协议规范](docs/MCP协议规范与实践.md) | MCP 协议详解 |
| [性能优化](docs/性能优化与跑分.md) | 缓存 + 并行调度指标 |

---

## License

MIT