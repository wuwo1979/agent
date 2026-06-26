<p align="center">
  <h1 align="center">MCP Agent Gateway</h1>
  <p align="center">
    <b>让 AI Agent 直接操控本地环境的 MCP 网关</b>
  </p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-blue?style=flat-square&logo=python">
  <img src="https://img.shields.io/badge/MCP-2024--11--05-green?style=flat-square">
  <img src="https://img.shields.io/badge/tests-105%20passing-brightgreen?style=flat-square">
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

**验证**：

```bash
curl -X POST http://localhost:9090/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"tools/list","params":{}}'
```

---

## 这是什么

MCP 协议让 AI IDE（Trae、Cursor 等）和外部平台（Dify、Ollama）通过标准接口调用本地工具。本项目是 **MCP 协议网关 + 工具集**，提供：

- **MCP JSON-RPC**：对接 Trae/Cursor/VS Code（HTTP 或 STDIO 模式）
- **REST API**：对接 Dify 工作流、Ollama 及其他 HTTP 客户端
- **18+ 内置工具**：文件系统、终端命令、数据库、网页抓取、大模型调用

```
AI Agent (Trae/Dify/Cursor)
        │
        ▼
┌─────────────────────────┐
│    MCP Agent Gateway    │
│  (HTTP / STDIO / REST)  │
└─────────────────────────┘
        │
        ▼
  文件系统 / 终端 / 数据库 / Ollama
```

---

## 生态适配

| 平台 | 方式 | 支持情况 |
|------|------|----------|
| **Trae IDE** | STDIO (MCP) | 标准 MCP 配置，可调全部 18+ 工具 |
| **Cursor** | STDIO / HTTP (MCP) | 同上，支持 setup_mcp.py 一键配置 |
| **VS Code** | STDIO / HTTP (MCP) | 通过 MCP 插件接入 |
| **Dify** | REST API | HTTP 自定义工具节点，自动发现工具列表 |
| **Ollama** | REST API | 内置 llm_call / llm_ping / llm_list_models |
| **curl / HTTP 客户端** | REST / MCP | 任意语言直接调用 |

---

## 运行方式

```bash
# HTTP 模式 —— 供 Dify / 浏览器 / curl 调用
python main.py --host 0.0.0.0 --port 9090

# STDIO 模式 —— 供 Trae / Cursor / VS Code 调用
python main.py --mode stdio

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

**Dify**：在 HTTP 请求节点配置 `POST http://localhost:9090/api/v1/tools/list` + `POST http://localhost:9090/api/v1/tools/call`

**Ollama**：启动 Ollama 后直接调用 `llm_call` / `llm_ping` / `llm_list_models` 工具

---

## 内置工具

| Provider | 工具 | 说明 |
|----------|------|------|
| **filesystem** | `read_file`, `write_file`, `list_dir`, `search_files`, `file_stat` | 路径隔离沙箱 |
| **terminal** | `run_command`, `sysinfo` | 命令黑/白名单 + 超时 |
| **database** | `query`, `execute`, `list_tables`, `describe_table` | 参数化防注入 |
| **web** | `web_fetch`, `web_api`, `json_query` | HTTP/HTTPS + 超时 |
| **llm** | `llm_call`, `llm_ping`, `llm_list_models` | Ollama 本地推理 |

全部 18+ 工具：`python main.py --demo`

---

## 架构概览

```
LLM/
├── mcp_gateway/           # MCP 协议网关 + 18+ 工具 + REST API + Agent
├── performance/           # 缓存 (命中率 ~50%) + 并行 (加速比 2.8x)
├── config/                # YAML 配置
├── core/                  # 基础设施
├── requirements/          # 依赖管理
├── tests/                 # 105 个测试
├── examples/              # 集成示例
├── scripts/               # setup_mcp.py 等工具
├── docker/                # Docker Compose (Ollama/ChromaDB/Milvus)
├── docs/                  # 学习笔记 + 接入指南
└── main.py                # 入口
```

---

## 测试

```bash
pytest                  # 全部 105 个测试
python main.py --test   # 同上
ruff check . --ignore=E501  # 代码风格
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