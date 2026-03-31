from core.agent_runtime.result_contract import build_structured_run_result, hydrate_legacy_result


def test_build_structured_run_result_extracts_answer_and_artifacts():
    result = build_structured_run_result(
        {
            "answer": "Ship the patch in two phases.",
            "review_findings": [
                {
                    "title": "Missing migration",
                    "severity": "high",
                    "description": "The new field is not persisted.",
                    "path": "db/alembic/versions/example.py",
                    "line": 12,
                }
            ],
            "sources": [
                {
                    "title": "Architecture Doc",
                    "url": "https://example.com/doc",
                    "snippet": "Structured outputs reduce rework.",
                }
            ],
            "code_files": [
                {
                    "path": "frontend-vue/src/store/agents.js",
                    "language": "javascript",
                    "content": "export const value = 1",
                }
            ],
        }
    )

    assert result["final_output"] == "Ship the patch in two phases."
    assert result["final_output_text"] == "Ship the patch in two phases."
    assert result["final_output_json"]["answer"] == "Ship the patch in two phases."
    artifact_types = [artifact["artifact_type"] for artifact in result["artifacts"]]
    assert "answer" in artifact_types
    assert "review_findings" in artifact_types
    assert "citations" in artifact_types
    assert "code_files" in artifact_types


def test_hydrate_legacy_result_backfills_text_and_artifacts():
    result = hydrate_legacy_result(
        final_output="Legacy markdown output",
        final_output_text=None,
        final_output_json=None,
        artifacts=[],
    )

    assert result["final_output"] == "Legacy markdown output"
    assert result["final_output_text"] == "Legacy markdown output"
    assert len(result["artifacts"]) == 1
    assert result["artifacts"][0]["artifact_type"] == "answer"
