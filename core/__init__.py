from pathlib import Path


_RUNTIME_CORE = Path(__file__).resolve().parent.parent / "ai_runtime" / "core"
__path__ = [str(_RUNTIME_CORE)]
