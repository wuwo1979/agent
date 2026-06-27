# Changelog

## v2.0.0 (2026-06-27)

### 架构升级 — 协议内核统一 + 传输层薄适配

#### 核心变化
- **唯一执行入口**: `MCPProtocolHandler.handle_request()` 成为唯一工具执行入口，消除 v1.3 双路径问题
- **HTTP 退化为纯适配器**: `ExternalAPIHandler` 降级为 REST → JSON-RPC 转换层，不再混入工具执行逻辑
- **可插拔中间件管道**: 引入 `MiddlewarePipeline` 参考 LangChain 设计，支持 before/after 钩子
  - before: [Auth] → [RateLimit] — 请求前置检查
  - after: [Audit] → [Cache] — 后置审计与缓存
- **错误码对齐 JSON-RPC 2.0**: 废弃自定义 -32000 错误码，全面迁移到标准错误码体系
- **会话上下文统一**: `SessionContext` 新增 `working_dir` / `path_cache` 跨传输层共享

### 新增功能

#### 高优先级
- **Ollama 代理层故障兜底** (#ollama-fault)
  - 新增 `/api/v1/ollama/health` 健康检查端点，返回 Ollama 服务详细状态
  - 10 种标准化错误码 (`OLLAMA_ERROR_MAP`): CUDA 崩溃 → `GPU_CRASH`, 连接失败 → `OLLAMA_DOWN` 等
  - 故障隔离设计：单模型崩溃不影响网关其他工具调用能力
  - 面试亮点：针对本地推理服务不稳定场景的故障隔离与降级
- **STDIO 日志严格隔离** (#stdio-clean)
  - `_redirect_all_stdout_logging()` 强制所有 Logger 输出到 stderr
  - stdout 只输出纯 JSON-RPC 消息，杜绝协议污染
  - 专项测试 `test_stdio_mode_stdout_purity` 验证 stdout 纯净性
- **会话上下文统一** (#session-ctx)
  - `SessionContext` 新增 `working_dir`, `path_cache` 字段
  - 同一 session_id 无论走 HTTP 还是 STDIO，上下文完全一致

#### 中优先级
- **OpenAPI Schema 端点** (#dify-openapi)
  - `/api/v1/openapi.json` 自动生成 Dify 兼容的 OpenAPI 3.0 Schema
  - 用户可在 Dify 中一键导入注册所有工具，无需手动配置 HTTP 节点
- **配置中心化** (#config-center)
  - 所有参数通过 `config/default.yaml` + `${VAR}` 环境变量控制
  - 端口、API 密钥、白名单目录、缓存大小、并发数无硬编码

#### 低优先级
- **工具参数 JSON Schema 标准化**: `ToolDefinition.to_mcp_format()` 自动添加 `additionalProperties: false` 和 `minLength: 1` 约束
- **流式输出统一校验**: 确认长耗时工具在 Dify (SSE) 和 Trae (JSON-RPC 通知) 两侧表现一致

### 测试
- 测试总量: 108 个（新增 STDIO 日志隔离专项测试）
- ruff 检查: 0 错误
- 双场景验证: Trae STDIO 模式 + Dify HTTP 模式均通过

---

## v1.3.0 (2026-06-25)

### 功能
- 基础 MCP 协议实现 (JSON-RPC 2.0)
- 5 大工具提供者: filesystem, terminal, database, web, llm
- 双传输层: HTTP (aiohttp) + STDIO (readline)
- 多租户管理 (API Key 隔离)
- 安全沙箱: 路径穿越防护, SQL 注入防护, 命令黑/白名单
- 审计日志环形缓冲区
- 性能缓存 + 并行调度
- 状态仪表盘 (`python main.py --status`)
- Docker 部署支持

### 测试
- 测试总量: 76 个
- ruff 检查: 0 错误