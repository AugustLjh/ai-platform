"""
URL Content Fetcher
"""
import asyncio
import aiohttp
from typing import Optional
from bs4 import BeautifulSoup


class URLFetcher:
    """URL内容抓取器"""

    def __init__(self, timeout: int = 30, max_size: int = 10 * 1024 * 1024):
        """
        初始化抓取器

        Args:
            timeout: 超时时间（秒）
            max_size: 最大内容大小（字节），默认10MB
        """
        self.timeout = timeout
        self.max_size = max_size

    async def fetch_text(self, url: str) -> tuple[str, str]:
        """
        抓取URL内容并提取文本

        Args:
            url: 目标URL

        Returns:
            (提取的文本, 页面标题)

        Raises:
            ValueError: URL无效或抓取失败
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                    headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                ) as response:
                    # 检查状态码
                    if response.status != 200:
                        raise ValueError(f"HTTP {response.status}: {response.reason}")

                    # 检查内容类型
                    content_type = response.headers.get('Content-Type', '').lower()
                    if 'text/html' not in content_type and 'application/xhtml' not in content_type:
                        raise ValueError(f"Unsupported content type: {content_type}")

                    # 检查内容大小
                    content_length = response.headers.get('Content-Length')
                    if content_length and int(content_length) > self.max_size:
                        raise ValueError(f"Content too large: {content_length} bytes")

                    # 读取内容
                    html_content = await response.text()

                    # 检查实际大小
                    if len(html_content.encode('utf-8')) > self.max_size:
                        raise ValueError("Content exceeds maximum size")

                    # 解析HTML
                    return self._extract_text(html_content)

        except aiohttp.ClientError as e:
            raise ValueError(f"Failed to fetch URL: {str(e)}")
        except asyncio.TimeoutError:
            raise ValueError(f"Timeout fetching URL (>{self.timeout}s)")
        except Exception as e:
            raise ValueError(f"Error fetching URL: {str(e)}")

    def _extract_text(self, html_content: str) -> tuple[str, str]:
        """
        从HTML中提取文本和标题

        Args:
            html_content: HTML内容

        Returns:
            (提取的文本, 页面标题)
        """
        soup = BeautifulSoup(html_content, 'html.parser')

        # 提取标题
        title_tag = soup.find('title')
        title = title_tag.get_text(strip=True) if title_tag else "Untitled"

        # 移除不需要的标签
        for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside']):
            tag.decompose()

        # 优先提取主要内容区域
        main_content = soup.find('main') or soup.find('article') or soup.find('body')

        if main_content:
            text = main_content.get_text(separator='\n', strip=True)
        else:
            text = soup.get_text(separator='\n', strip=True)

        # 清理多余空行
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        cleaned_text = '\n'.join(lines)

        return cleaned_text, title
