"""Agent runtime package.

This package collects the building blocks used by the agent runtime
(``runtime.py`` for the high-level service, ``planner``/``summarizer``/
``executor``/``intent`` for the per-phase collaborators, ``subagents/``
for the delegation primitives, ``skills/`` for the skill registry, …).

The ``__init__`` is intentionally empty: the heavyweight subclasses
(``AgentRuntime``, ``AgentPlanner``, etc.) live in submodules. They are
also imported from
:mod:`ai_runtime.graphs.agent.runtime` (``AgentOrchestrator``), and
eagerly exporting them here used to introduce a circular import.
"""
