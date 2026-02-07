"""
Abstract Base Class for Embedding Services
"""
from abc import ABC, abstractmethod
from typing import List


class EmbeddingService(ABC):
    """向量嵌入服务抽象基类"""

    @abstractmethod
    async def embed_text(self, text: str) -> List[float]:
        """
        将单个文本转换为向量

        Args:
            text: 输入文本

        Returns:
            向量表示（浮点数列表）
        """
        pass

    @abstractmethod
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        批量将文本转换为向量

        Args:
            texts: 输入文本列表

        Returns:
            向量列表
        """
        pass

    @abstractmethod
    def get_embedding_dimension(self) -> int:
        """
        获取向量维度

        Returns:
            向量维度数
        """
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """
        获取模型名称

        Returns:
            模型名称标识符
        """
        pass
