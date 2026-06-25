"""
RAG 知识库模块
基于 ChromaDB / Milvus 向量库，给 Agent 增加知识检索能力
"""

import hashlib
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("rag")


@dataclass
class Document:
    """文档对象"""
    id: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None


@dataclass
class SearchResult:
    """检索结果"""
    document: Document
    score: float
    rank: int


class EmbeddingProvider:
    """
    Embedding 提供者
    支持本地和云端 Embedding 模型
    """

    def __init__(self, provider: str = "ollama", model: str = "nomic-embed-text"):
        self.provider = provider
        self.model = model

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """批量文本向量化"""
        if self.provider == "ollama":
            return await self._embed_ollama(texts)
        elif self.provider == "openai":
            return await self._embed_openai(texts)
        else:
            # 本地简单实现（TF-IDF 风格，用于演示）
            return self._embed_simple(texts)

    async def _embed_ollama(self, texts: List[str]) -> List[List[float]]:
        """使用 Ollama Embedding"""
        import aiohttp

        url = os.getenv("OLLAMA_HOST", "http://localhost:11434") + "/api/embed"
        embeddings = []

        async with aiohttp.ClientSession() as session:
            for text in texts:
                async with session.post(url, json={
                    "model": self.model,
                    "input": text,
                }) as resp:
                    data = await resp.json()
                    embeddings.append(data["embeddings"][0])

        return embeddings

    async def _embed_openai(self, texts: List[str]) -> List[List[float]]:
        """使用 OpenAI Embedding"""
        import aiohttp

        api_key = os.getenv("OPENAI_API_KEY", "")
        url = "https://api.openai.com/v1/embeddings"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json={
                "model": "text-embedding-3-small",
                "input": texts,
            }) as resp:
                data = await resp.json()
                return [item["embedding"] for item in data["data"]]

    def _embed_simple(self, texts: List[str]) -> List[List[float]]:
        """简单本地 Embedding（基于字符哈希，仅用于演示）"""
        embeddings = []
        for text in texts:
            # 使用哈希生成伪 embedding
            vec = []
            for i in range(128):  # 128 维
                seed = hashlib.md5(f"{text}_{i}".encode()).hexdigest()
                val = int(seed[:8], 16) / 0xFFFFFFFF * 2 - 1  # 归一化到 [-1, 1]
                vec.append(val)
            embeddings.append(vec)
        return embeddings


class ChromaVectorStore:
    """
    ChromaDB 向量存储
    轻量级向量数据库，适合本地开发
    """

    def __init__(self, collection_name: str = "agent_knowledge",
                 persist_dir: str = "./chroma_data"):
        self.collection_name = collection_name
        self.persist_dir = persist_dir
        self._client = None
        self._collection = None

    def _ensure_client(self):
        """延迟初始化 ChromaDB 客户端"""
        if self._client is None:
            try:
                import chromadb
                from chromadb.config import Settings

                self._client = chromadb.Client(Settings(
                    chroma_db_impl="duckdb+parquet",
                    persist_directory=self.persist_dir,
                    anonymized_telemetry=False,
                ))

                self._collection = self._client.get_or_create_collection(
                    name=self.collection_name,
                    metadata={"hnsw:space": "cosine"},
                )
                logger.info(f"ChromaDB initialized: {self.collection_name}")
            except ImportError:
                logger.warning("chromadb not installed, using in-memory fallback")
                self._collection = InMemoryVectorStore()

    def add_documents(self, documents: List[Document]) -> int:
        """添加文档"""
        self._ensure_client()

        if not documents:
            return 0

        ids = [doc.id for doc in documents]
        contents = [doc.content for doc in documents]
        metadatas = [doc.metadata for doc in documents]

        if documents[0].embedding:
            embeddings = [doc.embedding for doc in documents]
            self._collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=contents,
                metadatas=metadatas,
            )
        else:
            self._collection.add(
                ids=ids,
                documents=contents,
                metadatas=metadatas,
            )

        logger.info(f"Added {len(documents)} documents to {self.collection_name}")
        return len(documents)

    def search(self, query: str, top_k: int = 5) -> List[SearchResult]:
        """语义搜索"""
        self._ensure_client()

        results = self._collection.query(
            query_texts=[query],
            n_results=top_k,
        )

        search_results = []
        if results["documents"] and results["documents"][0]:
            for i, doc_content in enumerate(results["documents"][0]):
                metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = results["distances"][0][i] if results["distances"] else 0
                score = 1.0 / (1.0 + distance) if distance else 1.0

                search_results.append(SearchResult(
                    document=Document(
                        id=results["ids"][0][i],
                        content=doc_content,
                        metadata=metadata,
                    ),
                    score=score,
                    rank=i + 1,
                ))

        return search_results

    def delete_collection(self):
        """删除集合"""
        if self._client:
            self._client.delete_collection(self.collection_name)
            self._collection = None
            logger.info(f"Deleted collection: {self.collection_name}")


class InMemoryVectorStore:
    """内存向量存储（ChromaDB 不可用时的降级方案）"""

    def __init__(self):
        self._documents: List[Document] = []

    def add(self, ids: List[str], documents: List[str],
            metadatas: List[Dict] = None, embeddings: List[List[float]] = None):
        for i, doc_id in enumerate(ids):
            self._documents.append(Document(
                id=doc_id,
                content=documents[i],
                metadata=metadatas[i] if metadatas else {},
                embedding=embeddings[i] if embeddings else None,
            ))

    def query(self, query_texts: List[str], n_results: int = 5) -> Dict[str, List]:
        """简单的关键词搜索（降级方案）"""
        query = query_texts[0].lower()
        scored = []

        for doc in self._documents:
            content_lower = doc.content.lower()
            # 简单的 TF 相似度
            score = sum(1 for word in query.split() if word in content_lower)
            scored.append((doc, score))

        scored.sort(key=lambda x: x[1], reverse=True)

        top = scored[:n_results]
        return {
            "ids": [[doc.id for doc, _ in top]],
            "documents": [[doc.content for doc, _ in top]],
            "metadatas": [[doc.metadata for doc, _ in top]],
            "distances": [[1.0 - s / max(1, len(query.split())) for _, s in top]],
        }


class RAGKnowledgeBase:
    """
    RAG 知识库
    整合 Embedding + 向量存储 + 检索，为 Agent 提供知识增强能力
    """

    def __init__(
        self,
        vector_store: Optional[ChromaVectorStore] = None,
        embedding_provider: Optional[EmbeddingProvider] = None,
    ):
        self.vector_store = vector_store or ChromaVectorStore()
        self.embedding = embedding_provider or EmbeddingProvider()

    async def add_knowledge(self, texts: List[str],
                            metadatas: Optional[List[Dict]] = None,
                            source: str = "manual") -> int:
        """
        添加知识条目
        Args:
            texts: 文本列表
            metadatas: 元数据列表
            source: 来源标识
        Returns:
            添加的文档数
        """
        documents = []
        for i, text in enumerate(texts):
            doc_id = hashlib.md5(f"{source}_{text[:50]}".encode()).hexdigest()[:16]
            metadata = (metadatas[i] if metadatas else {}) | {"source": source}
            documents.append(Document(
                id=doc_id,
                content=text,
                metadata=metadata,
            ))

        return self.vector_store.add_documents(documents)

    async def add_file(self, file_path: str) -> int:
        """
        从文件添加知识
        支持 .txt, .md, .json, .py
        """
        if not os.path.exists(file_path):
            logger.warning(f"File not found: {file_path}")
            return 0

        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        # 按段落分割
        chunks = self._chunk_text(content, chunk_size=500, overlap=50)
        metadatas = [{"file": file_path, "chunk": i} for i in range(len(chunks))]

        return await self.add_knowledge(chunks, metadatas, source=file_path)

    async def add_directory(self, dir_path: str, pattern: str = "*.py") -> int:
        """从目录批量添加文件"""
        import glob
        total = 0
        for file_path in glob.glob(os.path.join(dir_path, "**", pattern), recursive=True):
            if os.path.isfile(file_path):
                total += await self.add_file(file_path)
        return total

    async def search(self, query: str, top_k: int = 5) -> List[SearchResult]:
        """语义搜索知识库"""
        return self.vector_store.search(query, top_k)

    async def query_with_context(self, query: str, top_k: int = 5) -> str:
        """
        查询并返回格式化上下文
        直接用于注入 LLM prompt
        """
        results = await self.search(query, top_k)
        if not results:
            return "未找到相关知识。"

        context_parts = []
        for r in results:
            context_parts.append(
                f"[来源: {r.document.metadata.get('source', 'unknown')} | "
                f"相关度: {r.score:.2f}]\n{r.document.content}"
            )

        return "\n\n---\n\n".join(context_parts)

    def _chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
        """文本分块"""
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunks.append(text[start:end])
            start = end - overlap
        return chunks

    def get_stats(self) -> Dict[str, Any]:
        """获取知识库统计"""
        return {
            "collection": self.vector_store.collection_name,
            "embedding_model": self.embedding.model,
            "embedding_provider": self.embedding.provider,
        }


# ============================================================
# Milvus 向量存储（可选，生产级）
# ============================================================

class MilvusVectorStore:
    """
    Milvus 向量存储
    生产级向量数据库，支持大规模检索
    """

    def __init__(
        self,
        collection_name: str = "agent_knowledge",
        host: str = "localhost",
        port: int = 19530,
        dim: int = 768,
    ):
        self.collection_name = collection_name
        self.host = host
        self.port = port
        self.dim = dim
        self._connected = False

    def connect(self):
        """连接 Milvus"""
        try:
            from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, connections

            connections.connect(
                alias="default",
                host=self.host,
                port=self.port,
            )

            # 检查集合是否存在
            from pymilvus import utility
            if utility.has_collection(self.collection_name):
                self._collection = Collection(self.collection_name)
                self._collection.load()
            else:
                # 创建集合
                fields = [
                    FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=100, is_primary=True),
                    FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=65535),
                    FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=self.dim),
                    FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=500),
                ]
                schema = CollectionSchema(fields, description="Agent Knowledge Base")
                self._collection = Collection(self.collection_name, schema)

                # 创建索引
                index_params = {
                    "metric_type": "COSINE",
                    "index_type": "IVF_FLAT",
                    "params": {"nlist": 128},
                }
                self._collection.create_index("embedding", index_params)
                self._collection.load()

            self._connected = True
            logger.info(f"Milvus connected: {self.collection_name}")

        except ImportError:
            logger.warning("pymilvus not installed, falling back to ChromaDB")
            raise
        except Exception as e:
            logger.error(f"Milvus connection failed: {e}")
            raise

    def search(self, query_embedding: List[float], top_k: int = 5) -> List[Dict]:
        """向量搜索"""
        if not self._connected:
            self.connect()

        search_params = {"metric_type": "COSINE", "params": {"nprobe": 10}}
        results = self._collection.search(
            data=[query_embedding],
            anns_field="embedding",
            param=search_params,
            limit=top_k,
            output_fields=["content", "source"],
        )

        return [
            {
                "id": hit.id,
                "content": hit.entity.get("content", ""),
                "source": hit.entity.get("source", ""),
                "score": hit.score,
            }
            for hit in results[0]
        ]
