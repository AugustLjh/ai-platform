"""
Sentence Transformer Embedding Implementation
"""
import asyncio
from typing import List, Optional
import numpy as np
from .base import EmbeddingService


class SentenceTransformerEmbedding(EmbeddingService):
    """
    使用 sentence-transformers 库的嵌入服务
    支持多语言模型，适合中英文混合场景
    """

    def __init__(
        self,
        model_name: str = "paraphrase-multilingual-MiniLM-L12-v2",
        device: Optional[str] = None,
        cache_folder: Optional[str] = None,
    ):
        """
        初始化 Sentence Transformer 模型

        Args:
            model_name: 模型名称，默认使用多语言模型
                - paraphrase-multilingual-MiniLM-L12-v2: 轻量级多语言模型（推荐）
                - paraphrase-multilingual-mpnet-base-v2: 高精度多语言模型
                - all-MiniLM-L6-v2: 英文模型（速度快）
            device: 计算设备 ('cpu', 'cuda', None=自动检测)
            cache_folder: 模型缓存目录
        """
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError(
                "sentence-transformers not installed. "
                "Install it with: pip install sentence-transformers"
            )

        self.model_name = model_name
        self.device = device

        # 初始化模型（会自动下载）
        self.model = SentenceTransformer(
            model_name,
            device=device,
            cache_folder=cache_folder,
        )
        self.dimension = self.model.get_sentence_embedding_dimension()

    async def embed_text(self, text: str) -> List[float]:
        """
        将单个文本转换为向量

        Args:
            text: 输入文本

        Returns:
            向量表示
        """
        # 在线程池中运行同步模型推理
        loop = asyncio.get_event_loop()
        embedding = await loop.run_in_executor(
            None,
            lambda: self.model.encode(text, convert_to_numpy=True)
        )

        # 转换为列表
        return embedding.tolist()

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        批量将文本转换为向量（性能优化）

        Args:
            texts: 输入文本列表

        Returns:
            向量列表
        """
        if not texts:
            return []

        # 在线程池中运行批量推理
        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(
            None,
            lambda: self.model.encode(
                texts,
                convert_to_numpy=True,
                batch_size=32,  # 批量处理，提升性能
                show_progress_bar=False,
            )
        )

        # 转换为列表
        return [emb.tolist() for emb in embeddings]

    def get_embedding_dimension(self) -> int:
        """获取向量维度"""
        return self.dimension

    def get_model_name(self) -> str:
        """获取模型名称"""
        return self.model_name

    def compute_similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        """
        计算两个向量的余弦相似度

        Args:
            embedding1: 向量1
            embedding2: 向量2

        Returns:
            相似度分数 [0, 1]
        """
        vec1 = np.array(embedding1)
        vec2 = np.array(embedding2)

        # 余弦相似度
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        similarity = dot_product / (norm1 * norm2)
        # 归一化到 [0, 1]
        return float((similarity + 1) / 2)
