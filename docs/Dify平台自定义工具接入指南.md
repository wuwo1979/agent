# Dify 平台自定义工具接入指南

本指南说明如何将 MCP Gateway 作为**自定义工具节点**接入 Dify 工作流，让 Dify Agent 直接调用文件读写、终端命令、数据库查询、Ollama 大模型等 18+ 个本地工具。

## 架构

```
Dify 工作流
    │  HTTP POST (工具列表 / 工具调用)
    ▼
MCP Gateway (HTTP 模式, 端口 9090)
    │
    ▼
本地文件系统 / 终端 / SQLite / Ollama
```

## 前置条件

1. 已安装并启动 MCP Gateway
2. Dify 已部署并可以访问（本地或远程）
3. 如使用 Ollama 工具，确保 Ollama 已启动

## 接入步骤

### 1. 启动 MCP Gateway

```bash
# 在项目根目录
pip install -r requirements/runtime.txt
python main.py --host 0.0.0.0 --port 9090
```

确认服务正常：

```bash
curl http://localhost:9090/api/v1/health
# 预期返回: {"status": "ok", "tool_count": 18, ...}
```

### 2. 获取 AIP Key

默认密钥在 `config/default.yaml` 中：

```yaml
security:
  api_keys:
    - "mcp-gateway-dev-key-change-in-production"
```

### 3. 在 Dify 中添加自定义工具

进入 Dify 工作流 → **工具节点** → **创建自定义工具**：

#### 获取工具列表

- **名称**: `MCP Gateway`
- **请求方法**: `POST`
- **请求 URL**: `http://localhost:9090/api/v1/tools/list`
- **Headers**:
  - `Content-Type`: `application/json`
  - `X-API-Key`: `mcp-gateway-dev-key-change-in-production`
- **请求体**: `{}`

点击**获取工具列表**，Dify 将自动发现所有可用工具。

#### 配置工具调用

在自定义工具节点中配置：

- **请求方法**: `POST`
- **请求 URL**: `http://localhost:9090/api/v1/tools/call`
- **Headers**:
  - `Content-Type`: `application/json`
  - `X-API-Key`: `mcp-gateway-dev-key-change-in-production`
- **请求体**: `{"name": "{{tool_name}}", "arguments": {{tool_arguments}}}`

### 4. 在工作流中使用

在 Dify 工作流中添加 **MCP Gateway** 工具节点，选择要调用的工具。例如：

**读取文件**:
- 工具: `read_file`
- 参数: `{"path": "./README.md"}`

**执行终端命令**:
- 工具: `run_command`
- 参数: `{"command": "dir", "timeout": 10}`

**调用 Ollama 模型**:
- 工具: `llm_call`
- 参数: `{"model": "qwen2.5:7b", "prompt": "你好"}`

### 5. 验证接入

在 Dify 对话中输入：

```
查看当前项目的 README 文件
```

如果返回了文件内容，说明接入成功。

## 可用工具一览

| 工具 | HTTP 请求参数 | 适用场景 |
|------|---------------|----------|
| `read_file` | `{"path": "..."}` | 读取代码/配置文件 |
| `write_file` | `{"path": "...", "content": "..."}` | 自动生成文件 |
| `list_dir` | `{"path": "."}` | 浏览项目结构 |
| `run_command` | `{"command": "...", "timeout": 30}` | Git 操作、构建 |
| `sysinfo` | `{}` | 了解运行环境 |
| `query` | `{"sql": "SELECT * FROM ..."}` | 数据查询 |
| `llm_call` | `{"model": "...", "prompt": "..."}` | 本地大模型推理 |

完整工具列表：`curl -X POST http://localhost:9090/api/v1/tools/list`

## 安全说明

- 文件操作仅限 `MCP_WORKSPACE` 或 `MCP_FS_SAFE_ROOTS` 目录内
- 终端命令有 23 条黑名单（rm -rf /、shutdown 等），可选白名单模式
- 默认 API Key **仅限开发环境**使用，生产环境请修改 config/default.yaml

## 常见问题

**Q: Dify 提示 "无法获取工具列表"**

A: 检查 MCP Gateway 是否已启动，以及 URL 和 API Key 是否正确。可以通过 `curl` 测试：

```bash
curl -X POST http://localhost:9090/api/v1/tools/list \
  -H "X-API-Key: mcp-gateway-dev-key-change-in-production"
```

**Q: 工具调用返回 403**

A: API Key 不匹配，检查 config/default.yaml 中的 api_keys 配置。

**Q: 文件操作返回 "outside safe directories"**

A: 指定 `MCP_WORKSPACE` 环境变量或 `MCP_FS_SAFE_ROOTS`，确保路径在白名单内。