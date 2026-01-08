from typing import AsyncIterator, Callable, Any, Optional
from dataclasses import dataclass
import time


@dataclass
class StreamChunk:
    """Stream chunk with metadata"""
    content: str
    chunk_type: str = "content"  # content, thinking, tool_call, metadata, complete
    metadata: Optional[dict] = None
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


class StreamMiddleware:
    """Base middleware for stream processing"""

    async def process(self, chunk: StreamChunk) -> StreamChunk:
        """Process a stream chunk"""
        return chunk


class LoggingMiddleware(StreamMiddleware):
    """Middleware for logging stream chunks"""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.chunk_count = 0

    async def process(self, chunk: StreamChunk) -> StreamChunk:
        """Log chunk information"""
        self.chunk_count += 1
        if self.verbose:
            print(f"[Stream Log] Chunk {self.chunk_count}: type={chunk.chunk_type}, "
                  f"content_len={len(chunk.content)}")
        return chunk


class TokenCounterMiddleware(StreamMiddleware):
    """Middleware for counting tokens (simple word-based approximation)"""

    def __init__(self):
        self.token_count = 0

    async def process(self, chunk: StreamChunk) -> StreamChunk:
        """Count tokens in chunk"""
        if chunk.content:
            # Simple word-based token approximation
            tokens = len(chunk.content.split())
            self.token_count += tokens

            # Add token count to metadata
            if chunk.metadata is None:
                chunk.metadata = {}
            chunk.metadata['cumulative_tokens'] = self.token_count

        return chunk


class StreamPipeline:
    """Stream processing pipeline with middleware support"""

    def __init__(self, middlewares: Optional[list[StreamMiddleware]] = None):
        self.middlewares = middlewares or []

    def add_middleware(self, middleware: StreamMiddleware):
        """Add middleware to pipeline"""
        self.middlewares.append(middleware)

    async def process_stream(self,
                            source: AsyncIterator[Any],
                            transform: Optional[Callable[[Any], StreamChunk]] = None
                            ) -> AsyncIterator[StreamChunk]:
        """
        Process stream through middleware pipeline

        Args:
            source: Source async iterator
            transform: Optional transform function to convert source items to StreamChunk

        Yields:
            Processed StreamChunk objects
        """
        async for item in source:
            # Transform to StreamChunk if transform provided
            if transform:
                chunk = transform(item)
            elif isinstance(item, StreamChunk):
                chunk = item
            else:
                # Default: treat as string content
                chunk = StreamChunk(content=str(item))

            # Apply middlewares
            for middleware in self.middlewares:
                chunk = await middleware.process(chunk)

            yield chunk

    async def wrap_stream(self,
                         source: AsyncIterator[Any],
                         chunk_type: str = "content"
                         ) -> AsyncIterator[StreamChunk]:
        """
        Wrap a simple async iterator into StreamChunks

        Args:
            source: Source async iterator
            chunk_type: Type for all chunks

        Yields:
            StreamChunk objects
        """
        async for item in source:
            content = item if isinstance(item, str) else str(item)
            chunk = StreamChunk(content=content, chunk_type=chunk_type)

            # Apply middlewares
            for middleware in self.middlewares:
                chunk = await middleware.process(chunk)

            yield chunk
