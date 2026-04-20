import asyncio

from ai_runtime.core.agent_runtime.intent import IntentPreprocessor
from ai_runtime.core.agent_runtime.optimization import AgentRuntimeOptimizationConfig
from ai_runtime.core.agent_runtime.intent import IntentPreprocessor
from ai_runtime.core.agent_runtime.models import PlannerAction
from ai_runtime.core.agent_runtime.orchestrator import AgentOrchestrator


class _FailingLLMService:
    async def chat_with_candidates(self, *args, **kwargs):
        raise RuntimeError("llm unavailable")


def test_intent_preprocessor_heuristically_resolves_recent_reference():
    preprocessor = IntentPreprocessor()

    result = asyncio.run(
        preprocessor.preprocess(
            definition=type("Definition", (), {"system_prompt": ""})(),
            run_input={"message": "把它总结一下"},
            available_tools=[],
            runtime_context={
                "conversation": [
                    {"role": "user", "content": "这篇文章讨论向量数据库、RAG 评测和召回效果。"},
                    {"role": "assistant", "content": "我已经看完这篇文章的主要段落。"},
                    {"role": "user", "content": "把它总结一下"},
                ]
            },
            llm_service=_FailingLLMService(),
            llm_resolution={"candidates": [{}]},
        )
    )

    assert result["preprocess_source"] == "heuristic_fallback"
    assert result["inferred_intent"] == "summarize"
    assert result["should_answer_with_assumptions"] is True
    assert result["blocking_missing_information"] == []
    assert result["resolved_references"]
    assert "向量数据库" in result["resolved_references"][0]["resolved_to"]


def test_orchestrator_rejects_ask_user_for_non_blocking_ambiguity():
    orchestrator = object.__new__(AgentOrchestrator)

    approved, reason = orchestrator._approve_ask_user(
        action=PlannerAction(type="ask_user", title="Need more input", question="你指的是哪个？"),
        runtime_context={
            "intent_state": {
                "blocking_missing_information": [],
                "requires_user_decision": False,
                "should_answer_with_assumptions": True,
            },
            "step_history": [],
        },
        available_tools=[{"name": "web_search"}],
    )

    assert approved is False
    assert "assumptions" in reason


def test_orchestrator_allows_ask_user_for_blocking_user_decision_after_tool_attempts():
    orchestrator = object.__new__(AgentOrchestrator)

    approved, reason = orchestrator._approve_ask_user(
        action=PlannerAction(type="ask_user", title="Need target", question="你要我对比哪两个产品？"),
        runtime_context={
            "intent_state": {
                "blocking_missing_information": ["comparison targets"],
                "requires_user_decision": True,
                "should_answer_with_assumptions": False,
            },
            "step_history": [
                {"tool_name": "web_search", "status": "completed"},
                {"tool_name": "open_page", "status": "completed"},
            ],
        },
        available_tools=[{"name": "web_search"}, {"name": "open_page"}],
    )

    assert approved is True
    assert reason == "approved"


def test_intent_preprocessor_infers_review_intent():
    preprocessor = IntentPreprocessor()

    result = preprocessor._fallback_state(
        run_input={"message": "帮我 review 这次改动，找出 bug 和回归风险"},
        runtime_context={"conversation": []},
    )

    assert result["inferred_intent"] == "review"


def test_intent_preprocessor_infers_implement_intent():
    preprocessor = IntentPreprocessor()

    result = preprocessor._fallback_state(
        run_input={"message": "实现一个登录接口并修复 token 刷新逻辑"},
        runtime_context={"conversation": []},
    )

    assert result["inferred_intent"] == "implement"


def test_intent_preprocessor_short_circuits_explicit_request():
    preprocessor = IntentPreprocessor(
        optimization_config=AgentRuntimeOptimizationConfig(enable_intent_preprocess_short_circuit=True),
    )

    result = asyncio.run(
        preprocessor.preprocess(
            definition=type("Definition", (), {"system_prompt": ""})(),
            run_input={"message": "实现一个登录接口并修复 token 刷新逻辑"},
            available_tools=[],
            runtime_context={"conversation": []},
            llm_service=_FailingLLMService(),
            llm_resolution={"candidates": [{}]},
        )
    )

    assert result["preprocess_source"] == "short_circuit"
    assert result["normalized_message"] == "实现一个登录接口并修复 token 刷新逻辑"
    assert result["resolved_references"] == []
