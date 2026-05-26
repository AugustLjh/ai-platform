"""Text splitters tuned for the AI runtime."""
from .cjk_aware import CJKAwareTextSplitter
from .factory import build_splitter

__all__ = ["CJKAwareTextSplitter", "build_splitter"]
