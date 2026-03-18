from typing import Any, AsyncIterator, Dict
import os
import sys

# Add proto path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../proto"))

from core.chat import ChatRuntimeService


class ChatServiceImpl:
    """Compatibility adapter that routes chat and legacy agent requests."""

    def __init__(self):
        self.chat_runtime = ChatRuntimeService()
        self.sessions = self.chat_runtime.sessions

    async def stream_chat(self, request) -> AsyncIterator[Dict[str, Any]]:
        async for chunk in self.chat_runtime.stream_chat(request):
            yield chunk

    async def get_chat_history(self, request):
        return await self.chat_runtime.get_chat_history(request)
