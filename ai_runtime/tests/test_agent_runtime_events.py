from ai_runtime.core.agent_runtime.events import MASK, build_event_payload


def test_build_event_payload_masks_sensitive_values():
    payload = build_event_payload(
        arguments={
            "headers": {"Authorization": "Bearer secret-token"},
            "env": {"OPENAI_API_KEY": "sk-123"},
            "nested": {"client_secret": "top-secret"},
            "query": "safe",
        },
        metadata={"password_hint": "should-hide"},
        ok=True,
    )

    assert payload["arguments"]["headers"]["Authorization"] == MASK
    assert payload["arguments"]["env"]["OPENAI_API_KEY"] == MASK
    assert payload["arguments"]["nested"]["client_secret"] == MASK
    assert payload["arguments"]["query"] == "safe"
    assert payload["metadata"]["password_hint"] == MASK
    assert payload["ok"] is True
