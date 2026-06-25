"""
RAG 模块 - 知识库检索

状态: 🚧 待扩展
当前实现: ChromaDB 向量库基础封装（文档管理、向量检索、相似度搜索）
规划目标: 完整 RAG 管道（文档分块 → 向量化 → 检索增强 → 结果重排序）

依赖: pip install chromadb
"""
from rag.vector_store import (
    ChromaVectorStore,
    Document,
    EmbeddingProvider,
    InMemoryVectorStore,
    MilvusVectorStore,
    RAGKnowledgeBase,
    SearchResult,
)

__all__ = [
    "Document",
    "SearchResult",
    "EmbeddingProvider",
    "ChromaVectorStore",
    "MilvusVectorStore",
    "RAGKnowledgeBase",
    "InMemoryVectorStore",
]
