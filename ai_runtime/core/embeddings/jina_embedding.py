"""
Jina AI Embedding Implementation
使用 Jina AI API 进行文本嵌入（在线服务，支持多语言）
"""
from typing import List, Optional
import aiohttp
from .base import EmbeddingService


class JinaEmbedding(EmbeddingService):
    """
    使用 Jina AI API 的嵌入服务
    优点：免费额度大，支持多语言，无需下载模型
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "jina-embeddings-v3",
        api_base: Optional[str] = None,
        timeout: int = 30,
    ):
        """
        初始化 Jina Embedding 服务

        Args:
            api_key: Jina AI API 密钥（从 https://jina.ai/ 获取）
            model_name: 模型名称
                - jina-embeddings-v3: 1024维，多语言支持（推荐）
                - jina-embeddings-v2-base-zh: 768维，中文优化
            api_base: API 基础 URL
            timeout: 请求超时时间（秒）
        """
        self.api_key = api_key
        self.model_name = model_name
        self.api_base = api_base or "https://api.jina.ai/v1"
        self.timeout = timeout

        # 设置向量维度
        self.dimension_map = {
            "jina-embeddings-v3": 1024,
            "jina-embeddings-v2-base-zh": 768,
            "jina-embeddings-v2-base-en": 768,
        }
        self.dimension = self.dimension_map.get(model_name, 1024)

    async def embed_text(self, text: str) -> List[float]:
        """
        将单个文本转换为向量

        Args:
            text: 输入文本

        Returns:
            向量表示
        """
        result = await self.embed_batch([text])
        return result[0]

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        批量将文本转换为向量

        Args:
            texts: 输入文本列表

        Returns:
            向量列表
        """
        if not texts:
            return []

        url = f"{self.api_base}/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model_name,
            "input": texts,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(
                        f"Jina AI API error (status {response.status}): {error_text}"
                    )

                data = await response.json()
                embeddings = [item["embedding"] for item in data["data"]]
                return embeddings

    def get_embedding_dimension(self) -> int:
        """获取向量维度"""
        return self.dimension

    def get_model_name(self) -> str:
        """获取模型名称"""
        return self.model_name