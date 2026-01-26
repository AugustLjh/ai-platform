"""
OpenAI Embedding Implementation
使用 OpenAI API 进行文本嵌入（在线服务，无需下载模型）
"""
import asyncio
from typing import List, Optional
import aiohttp
from .base import EmbeddingService


class OpenAIEmbedding(EmbeddingService):
    """
    使用 OpenAI API 的嵌入服务
    优点：无需下载模型，直接调用在线API
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "text-embedding-3-small",
        api_base: Optional[str] = None,
        timeout: int = 30,
    ):
        """
        初始化 OpenAI Embedding 服务

        Args:
            api_key: OpenAI API 密钥
            model_name: 模型名称
                - text-embedding-3-small: 1536维，性价比高（推荐）
                - text-embedding-3-large: 3072维，质量更好
                - text-embedding-ada-002: 1536维，旧版本
            api_base: API 基础 URL（可选，用于代理或兼容服务）
            timeout: 请求超时时间（秒）
        """
        self.api_key = api_key
        self.model_name = model_name
        self.api_base = api_base or "https://api.openai.com/v1"
        self.timeout = timeout

        # 设置向量维度
        self.dimension_map = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
        }
        self.dimension = self.dimension_map.get(model_name, 1536)

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
                        f"OpenAI API error (status {response.status}): {error_text}"
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