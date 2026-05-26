from ai_runtime.core.agent_runtime.events import MASK, build_event_payload, sanitize_runtime_payload


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


def test_sanitize_runtime_payload_redacts_sensitive_text_patterns():
    payload = sanitize_runtime_payload(
        {
            "stdout": "Authorization: Bearer abcdefghijklmnop\napi_key=sk-1234567890abcdef",
            "notes": "normal deployment output",
        }
    )

    assert "abcdefghijklmnop" not in payload["stdout"]
    assert "sk-1234567890abcdef" not in payload["stdout"]
    assert payload["stdout"].count(MASK) >= 2
    assert payload["notes"] == "normal deployment output"
