from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import AsyncIterator, DefaultDict, Dict, List, Optional

from ai_runtime.core.agent_runtime.models import AgentRunEvent


class RuntimeStateStore:
    def __init__(self) -> None:
        self._subscribers: DefaultDict[str, List[asyncio.Queue[Optional[AgentRunEvent]]]] = defaultdict(list)
        self._cancelled: set[str] = set()
        self._tasks: Dict[str, asyncio.Task] = {}

    def register_task(self, run_id: str, task: asyncio.Task) -> None:
        self._tasks[run_id] = task

    def get_task(self, run_id: str) -> Optional[asyncio.Task]:
        return self._tasks.get(run_id)

    def clear_task(self, run_id: str) -> None:
        self._tasks.pop(run_id, None)

    def request_cancel(self, run_id: str) -> None:
        self._cancelled.add(run_id)

    def reset_cancel(self, run_id: str) -> None:
        self._cancelled.discard(run_id)

    def is_cancelled(self, run_id: str) -> bool:
        return run_id in self._cancelled

    async def publish(self, run_id: str, event: AgentRunEvent) -> None:
        for queue in list(self._subscribers.get(run_id, [])):
            await queue.put(event)

    async def close(self, run_id: str) -> None:
        for queue in self._subscribers.pop(run_id, []):
            await queue.put(None)

    async def close_all(self) -> None:
        for run_id in list(self._subscribers.keys()):
            await self.close(run_id)
        for task in list(self._tasks.values()):
            if not task.done():
                task.cancel()
        self._tasks.clear()

    async def subscribe(self, run_id: str) -> AsyncIterator[AgentRunEvent]:
        queue: asyncio.Queue[Optional[AgentRunEvent]] = asyncio.Queue()
        self._subscribers[run_id].append(queue)
        try:
            while True:
                item = await queue.get()
                if item is None:
                    return
                yield item
        finally:
            subscribers = self._subscribers.get(run_id, [])
            if queue in subscribers:
                subscribers.remove(queue)
            if not subscribers and run_id in self._subscribers:
                self._subscribers.pop(run_id, None)
