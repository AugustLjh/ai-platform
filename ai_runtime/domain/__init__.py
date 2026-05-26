"""Domain models — Pydantic types preserved across the LangChain/LangGraph rewrite.

These are the schema-level contracts shared between the API layer, graphs,
checkpointer mirrors, and persistence repositories. During the rewrite the
modules here re-export the existing definitions from `core/agent_runtime/models.py`
and `core/llm/messages.py`; once legacy code is removed the canonical
definitions move here verbatim.
"""
