# Trae IDE MCP 接入指南

本指南说明如何将 MCP Gateway 接入 Trae IDE，让 Trae 在对话中直接调用本项目的工具集（文件读写、终端命令、数据库查询、Ollama 大模型等）。

## 接入方式

本项目通过 **STDIO（标准输入/输出）** 模式与 Trae 通信，这是 Trae/Cursor/VS Code 等 AI IDE 原生支持的 MCP 传输协议。

## 配置步骤

### 1. 找到项目路径

打开终端，进入本项目根目录：

```bash
cd F:\python_projects\class\LLM
```

### 2. 获取 API Key

默认 API Key 在 `config/default.yaml` 中，如有自定义请替换：

```
mcp-gateway-dev-key-change-in-production
```

### 3. 在 Trae 中添加 MCP Server

在 Trae IDE 中：

- **Windows/Linux**: `设置 → MCP 服务 → 添加 MCP Server`
- 填入以下配置：

```json
{
  "mcpServers": {
    "agent-mcp-gateway": {
      "command": "python",
      "args": [
        "F:\\python_projects\\class\\LLM\\main.py",
        "--mode",
        "stdio"
      ],
      "env": {
        "MCP_API_KEY": "mcp-gateway-dev-key-change-in-production",
        "MCP_WORKSPACE": "F:\\python_projects\\class\\LLM"
      }
    }
  }
}
```

> **说明**：请将 `F:\\python_projects\\class\\LLM` 替换为你的实际项目路径。

### 4. 一键配置脚本

项目提供了自动配置脚本，可生成上述配置文件：

```bash
python scripts/setup_mcp.py
```

## 可用工具

接入后，Trae 可调用的工具包括：

| 工具 | 功能 |
|------|------|
| `sysinfo` | 获取操作系统、Python 版本等系统信息 |
| `read_file`, `write_file`, `edit_file`, `create_directory`, `list_files` | 文件系统操作 |
| `run_command`, `run_script` | 执行终端命令和脚本 |
| `query_db`, `execute_db`, `list_tables`, `describe_table` | 数据库操作 |
| `scrape_web`, `fetch_url` | 网页抓取 |
| `llm_call`, `llm_ping`, `llm_list_models` | Ollama 本地大模型调用 |
| `search_docs`, `search_knowledge` | 知识库检索 |

## 验证接入

在 Trae 对话中输入：

```
帮我用 sysinfo 工具查看当前系统和 Python 版本
```

如果返回了系统信息，说明接入成功。

## 常见问题

**Q: Trae 提示 "MCP Server 连接失败"**

A: 检查 Python 和 main.py 路径是否正确，确保已在项目根目录下运行过 `pip install -r requirements/runtime.txt`。

**Q: 工具调用超时**

A: 某些工具（如 Ollama 模型调用）首次启动有冷启动时间，后续调用会更快。可在 `config/default.yaml` 中调整 `timeout_ms`。