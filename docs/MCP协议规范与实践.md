# MCP 协议规范与实践

> Model Context Protocol (MCP) 官方协议规范 + 动手实践 + 2026 生态全景

---

## 零、2026 年 MCP 生态全景

### 0.1 关键数据（截至 2026 Q2）

| 指标 | 数据 |
|------|------|
| 活跃 MCP Server | 10,000+ |
| 月 SDK 下载量 | 9,700 万+ |
| 支持平台 | ChatGPT, Claude, Gemini, Cursor, VS Code, Replit |
| 治理归属 | Linux Foundation (Agentic AI Foundation) |
| 主流框架支持 | LangChain, CrewAI, Semantic Kernel, Spring AI |

### 0.2 2026 年三大协议分工

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│     MCP      │    │     A2A      │    │    AG-UI     │
│ Agent ↔ Tool │    │ Agent ↔ Agent│    │ Agent ↔ User │
│ (Anthropic)  │    │ (Google)     │    │ (CopilotKit) │
└──────────────┘    └──────────────┘    └──────────────┘
     工具调用           智能体协作          用户交互界面
```

### 0.3 MCP 2026 关键演进

1. **渐进式发现（Progressive Discovery）**：按需加载工具，不再预加载全部 → 减少上下文膨胀
2. **程序化工具调用（Programmatic Tool Calling）**：Agent 生成代码批量执行，而非逐个调用
3. **无状态传输（Stateless Transport）**：Google 参与推进，支持 Cloud Run/K8s 大规模部署
4. **Server Discovery**：Agent 可自动发现网站背后的 MCP 服务
5. **Skills over MCP**：领域知识直接随 Server 分发，弱化插件注册中心

---

## 一、MCP 协议概述

MCP（Model Context Protocol）是 Anthropic 于 2024 年 11 月推出的开放协议，2025 年 12 月捐赠给 Linux 基金会。用于标准化 AI 应用与外部工具/数据源之间的通信。

### 1.1 核心概念

```
┌─────────────────┐         JSON-RPC 2.0         ┌─────────────────┐
│   MCP Client    │ ◄──────────────────────────► │   MCP Server    │
│  (AI 应用/Agent) │                              │  (工具提供方)    │
└─────────────────┘                              └─────────────────┘
                                                         │
                                              ┌──────────┼──────────┐
                                              │          │          │
                                          文件系统     终端命令    数据库
```

### 1.2 协议版本

- 当前版本：`2024-11-05`（2025 年 12 月捐赠 Linux 基金会）
- 传输协议：JSON-RPC 2.0
- 传输方式：STDIO（进程通信）/ Streamable HTTP（推荐）/ SSE（服务端推送）

---

## 二、MCP 标准方法

### 2.1 生命周期方法

| 方法 | 描述 | 请求参数 | 响应 |
|------|------|----------|------|
| `initialize` | 初始化连接 | `protocolVersion`, `clientInfo` | `serverInfo`, `capabilities` |
| `ping` | 心跳检测 | 无 | `{}` |

### 2.2 工具方法

| 方法 | 描述 | 请求参数 | 响应 |
|------|------|----------|------|
| `tools/list` | 列出可用工具 | `category?` | `{tools: [...]}` |
| `tools/call` | 调用工具 | `name`, `arguments` | `{content: [...], isError}` |

### 2.3 资源方法

| 方法 | 描述 | 请求参数 | 响应 |
|------|------|----------|------|
| `resources/list` | 列出资源 | 无 | `{resources: [...]}` |
| `resources/read` | 读取资源 | `uri` | `{contents: [...]}` |

### 2.4 提示词方法

| 方法 | 描述 | 请求参数 | 响应 |
|------|------|----------|------|
| `prompts/list` | 列出提示词模板 | 无 | `{prompts: [...]}` |
| `prompts/get` | 获取提示词 | `name`, `arguments` | `{messages: [...]}` |

---

## 三、JSON-RPC 2.0 消息格式

### 3.1 请求格式

```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "method": "tools/call",
  "params": {
    "name": "fs_read_file",
    "arguments": {
      "path": "/app/config.json"
    }
  }
}
```

### 3.2 成功响应

```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"key\": \"value\"}"
      }
    ],
    "isError": false
  }
}
```

### 3.3 错误响应

```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "error": {
    "code": -32601,
    "message": "Method not found: unknown_method"
  }
}
```

### 标准错误码

| 错误码 | 含义 |
|--------|------|
| -32700 | Parse error（JSON 解析错误） |
| -32600 | Invalid Request（无效请求） |
| -32601 | Method not found（方法不存在） |
| -32602 | Invalid params（参数无效） |
| -32603 | Internal error（内部错误） |
| -32000 | Server error（服务器错误） |

---

## 四、动手实践：编写 2 个自定义 MCP 工具

### 4.1 工具 1：天气查询工具

```python
# weather_tool.py
import json
import aiohttp

async def get_weather(city: str, units: str = "metric") -> str:
    """
    查询城市天气
    Args:
        city: 城市名称
        units: 温度单位 (metric/imperial)
    """
    # 使用免费天气 API
    url = f"https://wttr.in/{city}?format=j1"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            
    current = data["current_condition"][0]
    return json.dumps({
        "city": city,
        "temperature": f"{current['temp_C']}°C",
        "humidity": f"{current['humidity']}%",
        "description": current["weatherDesc"][0]["value"],
        "wind_speed": f"{current['windspeedKmph']} km/h",
    }, ensure_ascii=False)

# 工具定义
WEATHER_TOOL_DEFINITION = {
    "name": "weather_get",
    "description": "查询指定城市的天气信息",
    "inputSchema": {
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "城市名称，如 Beijing, Shanghai"
            },
            "units": {
                "type": "string",
                "enum": ["metric", "imperial"],
                "default": "metric"
            }
        },
        "required": ["city"]
    }
}
```

### 4.2 工具 2：代码分析工具

```python
# code_analyzer.py
import ast
import json

async def analyze_code(file_path: str) -> str:
    """
    分析 Python 代码结构
    Args:
        file_path: Python 文件路径
    """
    with open(file_path, "r", encoding="utf-8") as f:
        source = f.read()
    
    tree = ast.parse(source)
    
    functions = []
    classes = []
    imports = []
    
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            functions.append({
                "name": node.name,
                "line": node.lineno,
                "args": [a.arg for a in node.args.args],
            })
        elif isinstance(node, ast.ClassDef):
            classes.append({
                "name": node.name,
                "line": node.lineno,
                "methods": [n.name for n in node.body 
                           if isinstance(n, ast.FunctionDef)],
            })
        elif isinstance(node, ast.Import):
            imports.extend([n.name for n in node.names])
        elif isinstance(node, ast.ImportFrom):
            imports.append(f"{node.module}.{node.names[0].name}")
    
    return json.dumps({
        "file": file_path,
        "lines": len(source.splitlines()),
        "functions": functions,
        "classes": classes,
        "imports": imports,
    }, ensure_ascii=False, indent=2)

CODE_ANALYZER_DEFINITION = {
    "name": "code_analyze",
    "description": "分析 Python 代码结构（函数、类、导入）",
    "inputSchema": {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Python 文件路径"
            }
        },
        "required": ["file_path"]
    }
}
```

### 4.3 注册到 MCP 网关

```python
from mcp_gateway.protocol import ToolRegistry, ToolDefinition

registry = ToolRegistry()

# 注册天气工具
registry.register(ToolDefinition(
    name="weather_get",
    description="查询城市天气",
    handler=get_weather,
    inputSchema=WEATHER_TOOL_DEFINITION["inputSchema"],
    category="external",
))

# 注册代码分析工具
registry.register(ToolDefinition(
    name="code_analyze",
    description="分析 Python 代码结构",
    handler=analyze_code,
    inputSchema=CODE_ANALYZER_DEFINITION["inputSchema"],
    category="development",
))
```

---

## 五、MCP 工具开发最佳实践

### 5.1 工具命名规范

- 格式：`{category}_{action}`
- 示例：`fs_read_file`, `db_query`, `term_run`
- 避免：`tool1`, `my_function`, `do_stuff`

### 5.2 输入 Schema 设计

```json
{
  "type": "object",
  "properties": {
    "path": {
      "type": "string",
      "description": "文件路径（必填）"
    },
    "encoding": {
      "type": "string",
      "default": "utf-8",
      "description": "编码格式（可选，默认 utf-8）"
    }
  },
  "required": ["path"]
}
```

### 5.3 错误处理

```python
async def safe_tool(**kwargs):
    try:
        # 业务逻辑
        result = do_something(kwargs)
        return json.dumps({"success": True, "data": result})
    except ValueError as e:
        return json.dumps({"error": f"Invalid parameter: {e}"})
    except Exception as e:
        return json.dumps({"error": f"Internal error: {e}"})
```

### 5.4 安全性

- 文件系统工具：路径白名单检查
- 终端命令：危险命令黑名单拦截
- 数据库：参数化查询防注入
- 网络请求：超时限制

---

## 六、本项目 MCP 实现亮点

1. **完整协议实现**：JSON-RPC 2.0 + 标准方法 + 错误码
2. **3 类 14 个内置工具**：文件系统(5) + 终端(3) + 数据库(5)
3. **双传输模式**：STDIO（本地）+ HTTP（远程）
4. **动态工具注册**：运行时注册/注销，支持第三方扩展
5. **依赖图管理**：自动识别工具依赖，支持并行调度
6. **安全沙箱**：路径白名单、命令黑名单、超时控制