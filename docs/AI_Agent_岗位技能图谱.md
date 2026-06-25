# AI 应用 / LLM Agent 岗位技能图谱

> 面向 AI 应用开发 / LLM Agent 工程师岗位的完整技能栈

---

## 一、核心技能矩阵

### 1. LLM 基础能力（必须精通）

| 技能 | 优先级 | 说明 | 本项目对应 |
|------|--------|------|------------|
| Prompt Engineering | ★★★★★ | System Prompt 设计、Few-shot、Chain-of-Thought | Agent 规划/校验 Prompt |
| Token 管理 | ★★★★ | Token 估算、上下文窗口优化、截断策略 | 增量上下文缓存 |
| Function Calling | ★★★★★ | 工具定义、参数 Schema、调用链路 | MCP 工具注册/调用 |
| 多模型适配 | ★★★★ | OpenAI/DeepSeek/Ollama API 统一封装 | 多模型适配器 |
| RAG 检索增强 | ★★★★ | Embedding、向量检索、知识注入 | ChromaDB/Milvus 集成 |

### 2. Agent 框架（必须掌握）

| 技能 | 优先级 | 说明 | 本项目对应 |
|------|--------|------|------------|
| LangGraph | ★★★★★ | 状态图、条件分支、子图拆分、Checkpoint | Agent 调度层核心 |
| LangChain | ★★★★ | Chain、Tool、Memory、Retriever | 工具链集成 |
| Multi-Agent 编排 | ★★★★ | 规划-执行-校验分工、Agent 通信 | 三 Agent 架构 |
| 失败重试与自愈 | ★★★★ | 指数退避、熔断、降级策略 | 重试管理器 |
| 状态持久化 | ★★★ | 断点续跑、快照恢复 | SnapshotManager |

### 3. MCP 协议（加分项）

| 技能 | 优先级 | 说明 | 本项目对应 |
|------|--------|------|------------|
| MCP 协议规范 | ★★★★★ | JSON-RPC 2.0、工具注册/调用/返回 | 完整 MCP 实现 |
| 自定义 MCP 工具 | ★★★★ | 文件系统、终端、数据库工具 | 3 类 14 个工具 |
| MCP 传输层 | ★★★ | STDIO 和 HTTP 双模式 | 传输层实现 |
| 第三方 MCP 集成 | ★★★ | 兼容外部 MCP 服务 | 可扩展架构 |

### 4. 性能优化（差异化亮点）

| 技能 | 优先级 | 说明 | 本项目对应 |
|------|--------|------|------------|
| 上下文缓存 | ★★★★ | 内容去重、增量压缩、LRU 淘汰 | 49.5% Token 压缩 |
| 并行调度 | ★★★★ | 依赖图分层、无依赖并行 | 2.9x 加速比 |
| 异步编程 | ★★★★ | asyncio、协程、并发控制 | 全异步架构 |
| 模型推理优化 | ★★★ | vLLM 部署、GPU 利用率 | vLLM 适配层 |

### 5. 工程化能力（必备）

| 技能 | 优先级 | 说明 | 本项目对应 |
|------|--------|------|------------|
| Docker Compose | ★★★★ | 一键部署、服务编排 | 完整 docker-compose |
| RESTful API 设计 | ★★★★ | HTTP 接口、错误处理 | MCP HTTP 传输 |
| 单元测试 | ★★★★ | pytest、覆盖率 | 测试套件 |
| 性能测试 | ★★★ | Benchmark、跑分 | 跑分系统 |
| 向量数据库 | ★★★ | ChromaDB、Milvus | RAG 知识库 |

---

## 二、面试高频考点

### 2.1 Agent 架构设计

**Q: 如何设计一个多 Agent 协作系统？**

关键点：
1. **规划 Agent**：将用户意图拆解为子任务 DAG，识别依赖关系
2. **执行 Agent**：按拓扑顺序执行，无依赖任务并行，带重试机制
3. **校验 Agent**：验证执行结果，不合格则触发重新规划
4. **状态管理**：全局状态快照，支持断点续跑

**Q: LangGraph 的优势是什么？**

- 基于图的状态机，支持条件分支和循环
- 内置 Checkpoint 机制，天然支持断点续跑
- 节点可嵌套子图，支持复杂 Agent 编排
- 与 LangChain 生态无缝集成

### 2.2 MCP 协议

**Q: MCP 协议的核心设计思想？**

- **客户端-服务器架构**：AI 应用作为客户端，工具提供方作为服务器
- **JSON-RPC 2.0**：标准化的请求/响应格式
- **工具发现**：`tools/list` 动态获取可用工具
- **安全性**：工具调用可限制权限范围

**Q: 如何实现自定义 MCP 工具？**

1. 定义工具 Schema（name, description, inputSchema）
2. 实现工具处理函数
3. 注册到 ToolRegistry
4. 通过 `tools/call` 接口调用

### 2.3 性能优化

**Q: 如何减少 Agent 的 Token 消耗？**

- **增量上下文缓存**：相同工具调用结果不重复传回（本项目实现 49.5% 压缩）
- **上下文压缩**：超长结果自动截断 + 摘要
- **增量差异**：只传回变化部分
- **智能截断**：保留关键信息，裁剪冗余

**Q: 如何提升多工具调用的执行效率？**

- **依赖图分析**：识别无依赖工具，并行执行
- **拓扑分层**：同层工具并发，不同层串行
- **并发控制**：Semaphore 限制最大并发数
- **异步 I/O**：避免阻塞等待

---

## 三、学习路线图

```
第1周：LLM 基础
├── OpenAI API 调用（Chat Completion）
├── Prompt Engineering 实践
├── Function Calling 工具定义
└── Token 计算与优化

第2周：Agent 框架
├── LangChain 基础（Chain、Tool、Memory）
├── LangGraph 状态图入门
├── ReAct Agent 实现
└── Multi-Agent 协作

第3周：MCP 协议 + 工具开发
├── MCP 协议规范学习
├── 自定义工具开发（文件/终端/数据库）
├── 工具注册与调用链路
└── 第三方 MCP 集成

第4周：工程化 + 部署
├── Docker Compose 打包
├── 向量数据库（ChromaDB/Milvus）
├── RAG 知识库集成
├── vLLM 本地部署
└── 性能测试与优化
```

---

## 四、简历关键词

适合放入简历的技术关键词：

```
MCP 协议 | LangGraph | Multi-Agent | 增量上下文缓存 | 并行工具调度
Token 优化 | RAG 检索增强 | vLLM 本地推理 | Docker Compose
ChromaDB | Milvus | 多模型适配 | 断点续跑 | 熔断重试
```

---

## 五、参考资源

- MCP 官方规范：https://spec.modelcontextprotocol.io/
- LangGraph 文档：https://langchain-ai.github.io/langgraph/
- vLLM 项目：https://github.com/vllm-project/vllm
- ChromaDB 文档：https://docs.trychroma.com/
- Milvus 文档：https://milvus.io/docs/