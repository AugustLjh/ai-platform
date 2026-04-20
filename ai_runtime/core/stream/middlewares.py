from .pipeline import StreamMiddleware, StreamChunk
import time


class RateLimitMiddleware(StreamMiddleware):
    """Middleware to limit streaming rate"""

    def __init__(self, min_interval: float = 0.01):
        """
        Args:
            min_interval: Minimum interval between chunks in seconds
        """
        self.min_interval = min_interval
        self.last_time = 0.0

    async def process(self, chunk: StreamChunk) -> StreamChunk:
        """Apply rate limiting"""
        import asyncio

        current_time = time.time()
        elapsed = current_time - self.last_time

        if elapsed < self.min_interval and self.last_time > 0:
            await asyncio.sleep(self.min_interval - elapsed)

        self.last_time = time.time()
        return chunk


class ContentFilterMiddleware(StreamMiddleware):
    """Middleware to filter inappropriate content"""

    def __init__(self, blocked_words: list[str] = None):
        self.blocked_words = [w.lower() for w in (blocked_words or [])]

    async def process(self, chunk: StreamChunk) -> StreamChunk:
        """Filter content"""
        if chunk.content and self.blocked_words:
            content_lower = chunk.content.lower()
            for word in self.blocked_words:
                if word in content_lower:
                    chunk.content = chunk.content.replace(word, "***")

        return chunk


class CostTrackingMiddleware(StreamMiddleware):
    """Middleware to track cost of tokens"""

    def __init__(self, cost_per_1k_tokens: float = 0.002):
        self.cost_per_1k_tokens = cost_per_1k_tokens
        self.total_cost = 0.0
        self.total_tokens = 0

    async def process(self, chunk: StreamChunk) -> StreamChunk:
        """Track cost"""
        if chunk.content:
            tokens = len(chunk.content.split())
            self.total_tokens += tokens
            self.total_cost = (self.total_tokens / 1000) * self.cost_per_1k_tokens

            if chunk.metadata is None:
                chunk.metadata = {}
            chunk.metadata['total_cost'] = round(self.total_cost, 6)

        return chunk
