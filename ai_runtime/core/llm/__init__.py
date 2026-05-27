"""Multimodal message + capability helpers shared with the LangChain stack.

After P8.3 the legacy ``BaseLLM`` provider hierarchy is gone; this package
only exposes the message/capability primitives in ``messages.py`` (still
used by the chat-graph helpers, the agent runtime, and the API layer).

Submodules are imported explicitly by their callers — the package
``__init__`` stays empty to break the eager dependency chain on the
LangChain-side ``ai_runtime.llm`` package (whose ``__init__`` imports
``capability`` which in turn imports back here).

The LangChain ``BaseChatModel`` factory + provider subclasses live in
``ai_runtime.llm``.
"""
