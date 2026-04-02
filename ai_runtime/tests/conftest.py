from __future__ import annotations

import asyncio
import inspect
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
AI_RUNTIME_ROOT = PROJECT_ROOT / "ai_runtime"

for candidate in (str(PROJECT_ROOT), str(AI_RUNTIME_ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)


def pytest_configure(config) -> None:
    config.addinivalue_line("markers", "asyncio: run the test inside a default asyncio event loop")


def pytest_pyfunc_call(pyfuncitem):
    test_function = pyfuncitem.obj
    if not inspect.iscoroutinefunction(test_function):
        return None

    kwargs = {
        name: pyfuncitem.funcargs[name]
        for name in pyfuncitem._fixtureinfo.argnames
        if name in pyfuncitem.funcargs
    }
    asyncio.run(test_function(**kwargs))
    return True
