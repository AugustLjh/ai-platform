"""
File Parsers for Knowledge Base
"""
import os
from abc import ABC, abstractmethod
from typing import Optional


class FileParser(ABC):
    """文件解析器抽象基类"""

    @abstractmethod
    async def parse(self, file_content: bytes, filename: str) -> str:
        """
        解析文件内容为文本

        Args:
            file_content: 文件二进制内容
            filename: 文件名

        Returns:
            解析后的文本内容
        """
        pass

    @staticmethod
    def get_parser(filename: str) -> Optional["FileParser"]:
        """
        根据文件名获取对应的解析器

        Args:
            filename: 文件名

        Returns:
            对应的解析器，如果不支持则返回None
        """
        ext = os.path.splitext(filename)[1].lower()

        parsers = {
            ".txt": TextParser(),
            ".md": MarkdownParser(),
            ".pdf": PDFParser(),
            ".html": HTMLParser(),
            ".htm": HTMLParser(),
        }

        return parsers.get(ext)

    @staticmethod
    def is_supported(filename: str) -> bool:
        """检查文件类型是否支持"""
        return FileParser.get_parser(filename) is not None


class TextParser(FileParser):
    """纯文本解析器"""

    async def parse(self, file_content: bytes, filename: str) -> str:
        """解析文本文件"""
        # 尝试多种编码
        encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']

        for encoding in encodings:
            try:
                return file_content.decode(encoding)
            except UnicodeDecodeError:
                continue

        # 如果都失败，使用 utf-8 并忽略错误
        return file_content.decode('utf-8', errors='ignore')


class MarkdownParser(FileParser):
    """Markdown解析器"""

    async def parse(self, file_content: bytes, filename: str) -> str:
        """解析Markdown文件（保留原始格式）"""
        encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']

        for encoding in encodings:
            try:
                return file_content.decode(encoding)
            except UnicodeDecodeError:
                continue

        return file_content.decode('utf-8', errors='ignore')


class PDFParser(FileParser):
    """PDF解析器"""

    async def parse(self, file_content: bytes, filename: str) -> str:
        """
        解析PDF文件

        需要安装：pip install PyPDF2
        """
        try:
            from PyPDF2 import PdfReader
            from io import BytesIO
        except ImportError:
            raise ImportError(
                "PyPDF2 not installed. Install it with: pip install PyPDF2"
            )

        try:
            pdf_file = BytesIO(file_content)
            reader = PdfReader(pdf_file)

            text_parts = []
            for page_num, page in enumerate(reader.pages, 1):
                text = page.extract_text()
                if text.strip():
                    text_parts.append(f"=== Page {page_num} ===\n{text}")

            return "\n\n".join(text_parts)

        except Exception as e:
            raise ValueError(f"Failed to parse PDF: {str(e)}")


class HTMLParser(FileParser):
    """HTML解析器"""

    async def parse(self, file_content: bytes, filename: str) -> str:
        """
        解析HTML文件，提取纯文本

        需要安装：pip install beautifulsoup4
        """
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            raise ImportError(
                "beautifulsoup4 not installed. Install it with: pip install beautifulsoup4"
            )

        try:
            # 尝试检测编码
            encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
            html_content = None

            for encoding in encodings:
                try:
                    html_content = file_content.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue

            if html_content is None:
                html_content = file_content.decode('utf-8', errors='ignore')

            # 使用BeautifulSoup提取文本
            soup = BeautifulSoup(html_content, 'html.parser')

            # 移除script和style标签
            for script in soup(['script', 'style']):
                script.decompose()

            # 获取文本
            text = soup.get_text(separator='\n', strip=True)

            # 清理多余的空行
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            return '\n'.join(lines)

        except Exception as e:
            raise ValueError(f"Failed to parse HTML: {str(e)}")
