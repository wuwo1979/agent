"""
RAG 模块 - 知识库检索

基于 ChromaDB / Milvus 的知识库检索模块。
支持文档管理、向量检索、相似度搜索和知识库增强。

依赖: pip install chromadb
"""
from mcp_gateway.rag.vector_store import (
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
