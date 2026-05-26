from ai_runtime.core.agent_runtime.models import AgentArtifact
from ai_runtime.core.agent_runtime.events import MASK
from ai_runtime.contracts import (
    build_artifacts_from_tool_result,
    build_structured_run_result,
    hydrate_legacy_result,
    merge_artifacts,
)


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


def test_build_structured_run_result_redacts_sensitive_artifact_payloads():
    result = build_structured_run_result(
        {
            "answer": "Token is token=super-secret-token-value",
            "table": {
                "rows": [
                    {
                        "name": "env",
                        "api_key": "sk-1234567890abcdef",
                    }
                ],
            },
        }
    )

    serialized = str(result["artifacts"])
    assert "super-secret-token-value" not in serialized
    assert "sk-1234567890abcdef" not in serialized
    assert MASK in serialized


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


def test_hydrate_legacy_result_merges_partial_artifacts_with_derived_result_surface():
    result = hydrate_legacy_result(
        final_output=None,
        final_output_text=None,
        final_output_json={
            "steps": [
                {"title": "Audit compatibility drift", "status": "in_progress"},
                {"title": "Backfill replay coverage", "status": "pending"},
            ],
            "citations": [
                {
                    "title": "Runtime Plan",
                    "url": "https://example.com/runtime-plan",
                    "snippet": "Prefer structure-first hydration.",
                }
            ],
        },
        artifacts=[
            {
                "artifact_type": "citations",
                "name": "Runtime Sources",
                "payload": {
                    "items": [
                        {
                            "title": "Runtime Plan",
                            "url": "https://example.com/runtime-plan",
                            "snippet": "Prefer structure-first hydration.",
                        }
                    ]
                },
            }
        ],
    )

    assert result["final_output_text"] == "Audit compatibility drift\nBackfill replay coverage"
    artifact_types = [artifact["artifact_type"] for artifact in result["artifacts"]]
    assert artifact_types == ["answer", "citations", "task_plan"]
    assert result["artifacts"][1]["name"] == "Runtime Sources"


def test_build_structured_run_result_derives_task_plan_and_text_from_steps_only_payload():
    result = build_structured_run_result(
        {
            "steps": [
                {"title": "Audit the current compatibility layer", "status": "in_progress"},
                {"title": "Backfill hydration coverage", "status": "pending"},
            ],
            "decisions": ["Prefer compatibility-safe shaping before larger refactors."],
        }
    )

    assert result["final_output_json"]["task_plan"]["steps"][0]["title"] == "Audit the current compatibility layer"
    assert result["artifacts"][1]["artifact_type"] == "task_plan"
    assert result["final_output_text"] == "Audit the current compatibility layer\nBackfill hydration coverage"


def test_build_structured_run_result_uses_nested_excerpt_and_findings_as_text_fallback():
    excerpt_result = build_structured_run_result(
        {
            "document_excerpt": [
                {
                    "title": "Runtime Notes",
                    "text": "The structured payload must survive refresh hydration.",
                }
            ]
        }
    )
    findings_result = build_structured_run_result(
        {
            "review_findings": [
                {
                    "title": "Missing execution reset",
                    "description": "Resume currently leaks old artifacts into the new attempt.",
                }
            ]
        }
    )

    assert excerpt_result["final_output_text"] == "The structured payload must survive refresh hydration."
    assert findings_result["final_output_text"] == "Missing execution reset"


def test_build_artifacts_from_tool_result_promotes_structured_tool_payload_without_answer_duplication():
    artifacts = build_artifacts_from_tool_result(
        {
            "structured_content": {
                "answer": "Two matching documents found.",
                "citations": [
                    {
                        "title": "Runtime Plan",
                        "url": "https://example.com/runtime-plan",
                        "snippet": "Use structured artifacts.",
                    }
                ],
                "table": {
                    "columns": ["name", "status"],
                    "rows": [{"name": "catalog", "status": "ready"}],
                },
            },
            "text": "Two matching documents found.",
        },
        tool_name="search_docs",
        tool_kind="mcp",
        step_id="step-1",
        tool_call_id="tool-call-1",
        include_answer=False,
    )

    artifact_types = [artifact["artifact_type"] for artifact in artifacts]
    assert "answer" not in artifact_types
    assert "citations" in artifact_types
    assert "table" in artifact_types
    assert artifacts[0]["metadata"]["tool_call_id"] == "tool-call-1"


def test_build_artifacts_from_tool_result_redacts_sensitive_tool_outputs():
    artifacts = build_artifacts_from_tool_result(
        {
            "content": [
                {
                    "type": "text",
                    "text": "Bearer abcdefghijklmnop",
                    "metadata": {"authorization": "Bearer secret"},
                }
            ]
        },
        tool_name="mcp_fetch",
        tool_kind="mcp",
        step_id="step-1",
        tool_call_id="tool-call-1",
    )

    serialized = str(artifacts)
    assert "abcdefghijklmnop" not in serialized
    assert "Bearer secret" not in serialized


def test_build_artifacts_from_mcp_governance_result_promotes_safe_summary():
    artifacts = build_artifacts_from_tool_result(
        {
            "servers": [
                {
                    "server": {"id": "server-1", "name": "Docs MCP", "transport": "http", "status": "active"},
                    "availability": {"status": "available"},
                    "recovery": {"summary": "refresh first", "status": "stale"},
                    "security_score": {"risk_level": "medium", "score": 71, "summary": "watch"},
                }
            ],
            "summary": {"total_servers": 1},
            "tenant_id": "tenant-1",
        },
        tool_name="mcp_catalog_status",
        tool_kind="mcp-governance",
        step_id="step-1",
        tool_call_id="tool-call-1",
    )

    artifact_types = [artifact["artifact_type"] for artifact in artifacts]
    assert "paged_collection" in artifact_types
    paged = next(artifact for artifact in artifacts if artifact["artifact_type"] == "paged_collection")
    assert paged["payload"]["items"][0]["server_name"] == "Docs MCP"
    assert paged["payload"]["items"][0]["risk_level"] == "medium"


def test_build_artifacts_from_tool_result_promotes_workspace_patch_artifact():
    artifacts = build_artifacts_from_tool_result(
        {
            "status": "applied",
            "path": "src/app.py",
            "operation": "modify",
            "dry_run": False,
            "changed": True,
            "before_sha256": "before",
            "after_sha256": "after",
            "diff": "--- a/src/app.py\n+++ b/src/app.py\n@@\n-old\n+new\n",
            "artifacts": [
                {
                    "artifact_type": "code_patch",
                    "name": "Workspace Patch",
                    "payload": {
                        "operation": "modify",
                        "status": "applied",
                        "dry_run": False,
                        "files": [
                            {
                                "path": "src/app.py",
                                "operation": "modify",
                                "before_sha256": "before",
                                "after_sha256": "after",
                                "changed": True,
                            }
                        ],
                        "diff": "--- a/src/app.py\n+++ b/src/app.py\n@@\n-old\n+new\n",
                    },
                }
            ],
        },
        tool_name="workspace_apply_patch",
        tool_kind="workspace",
        step_id="step-1",
        tool_call_id="tool-call-1",
    )

    assert len(artifacts) == 1
    assert artifacts[0]["artifact_type"] == "code_patch"
    assert artifacts[0]["payload"]["files"][0]["path"] == "src/app.py"
    assert artifacts[0]["metadata"]["tool_call_id"] == "tool-call-1"
    assert artifacts[0]["metadata"]["operation"] == "modify"


def test_build_artifacts_from_tool_result_promotes_delete_patch_metadata():
    artifacts = build_artifacts_from_tool_result(
        {
            "status": "dry_run",
            "path": "src/obsolete.py",
            "operation": "delete",
            "dry_run": True,
            "changed": True,
            "before_sha256": "before",
            "after_sha256": None,
            "diff": "--- a/src/obsolete.py\n+++ b/src/obsolete.py\n@@\n-old\n",
            "artifacts": [
                {
                    "artifact_type": "code_patch",
                    "name": "Workspace Patch",
                    "payload": {
                        "operation": "delete",
                        "status": "dry_run",
                        "dry_run": True,
                        "files": [
                            {
                                "path": "src/obsolete.py",
                                "operation": "delete",
                                "before_sha256": "before",
                                "after_sha256": None,
                                "changed": True,
                            }
                        ],
                        "diff": "--- a/src/obsolete.py\n+++ b/src/obsolete.py\n@@\n-old\n",
                        "review_notes": ["Deletion requires review."],
                        "merge_policy": "manual_review_required",
                    },
                }
            ],
        },
        tool_name="workspace_delete_path",
        tool_kind="workspace",
        tool_call_id="tool-call-2",
    )

    assert len(artifacts) == 1
    assert artifacts[0]["artifact_type"] == "code_patch"
    assert artifacts[0]["payload"]["operation"] == "delete"
    assert artifacts[0]["payload"]["review_notes"] == ["Deletion requires review."]
    assert artifacts[0]["payload"]["merge_policy"] == "manual_review_required"
    assert artifacts[0]["metadata"]["tool_call_id"] == "tool-call-2"


def test_build_structured_run_result_promotes_implicit_result_lists_into_table_artifacts():
    result = build_structured_run_result(
        {
            "answer": "Found two matching records.",
            "results": [
                {"path": "/docs/runtime", "status": "ready"},
                {"path": "/docs/mcp", "status": "stale"},
            ],
        }
    )

    assert result["final_output_text"] == "Found two matching records."
    assert any(artifact["artifact_type"] == "table" and artifact["name"] == "Results" for artifact in result["artifacts"])


def test_build_structured_run_result_promotes_paginated_results_and_rich_resources():
    result = build_structured_run_result(
        {
            "results": [
                {"path": "/docs/runtime", "status": "ready"},
                {"path": "/docs/mcp", "status": "stale"},
            ],
            "next_cursor": "cursor-2",
            "total_count": 42,
            "images": [
                {
                    "title": "Workspace Architecture",
                    "uri": "https://example.com/architecture.png",
                    "mimeType": "image/png",
                }
            ],
            "attachments": [
                {
                    "name": "catalog-export.pdf",
                    "uri": "https://example.com/catalog-export.pdf",
                    "mimeType": "application/pdf",
                    "sizeBytes": 2048,
                }
            ],
        }
    )

    artifact_types = [artifact["artifact_type"] for artifact in result["artifacts"]]
    assert "paged_collection" in artifact_types
    assert "media_gallery" in artifact_types
    assert "file_bundle" in artifact_types
    paged = next(artifact for artifact in result["artifacts"] if artifact["artifact_type"] == "paged_collection")
    assert paged["payload"]["pagination"]["next_cursor"] == "cursor-2"
    assert paged["payload"]["pagination"]["total_count"] == 42
    media = next(artifact for artifact in result["artifacts"] if artifact["artifact_type"] == "media_gallery")
    assert media["payload"]["items"][0]["kind"] == "image"
    bundle = next(artifact for artifact in result["artifacts"] if artifact["artifact_type"] == "file_bundle")
    assert bundle["payload"]["files"][0]["name"] == "catalog-export.pdf"


def test_build_structured_run_result_promotes_directory_tree_document_pages_and_archive_bundle():
    result = build_structured_run_result(
        {
            "directory_tree": [
                {"path": "src/components/AgentArtifactPanel.vue", "type": "file", "size_bytes": 2048},
                {"path": "src/utils/agentArtifacts.js", "type": "file", "size_bytes": 4096},
                {"path": "tests/", "type": "directory"},
            ],
            "document_pages": {
                "title": "Catalog Export",
                "page_count": 2,
                "pages": [
                    {"page": 1, "text": "Overview of the exported catalog."},
                    {"page": 2, "text": "Detailed tool metadata.", "thumbnail_uri": "https://example.com/page-2.png"},
                ],
            },
            "archive_bundle": {
                "name": "workspace-export.zip",
                "format": "zip",
                "entries": [
                    {"path": "src/components/AgentArtifactPanel.vue", "size_bytes": 2048, "compressed_size_bytes": 512},
                    {"path": "src/utils/agentArtifacts.js", "size_bytes": 4096, "compressed_size_bytes": 1024},
                ],
            },
        }
    )

    artifact_types = [artifact["artifact_type"] for artifact in result["artifacts"]]
    assert "directory_tree" in artifact_types
    assert "document_pages" in artifact_types
    assert "archive_bundle" in artifact_types
    directory_tree = next(artifact for artifact in result["artifacts"] if artifact["artifact_type"] == "directory_tree")
    assert directory_tree["payload"]["summary"]["file_count"] == 2
    document_pages = next(artifact for artifact in result["artifacts"] if artifact["artifact_type"] == "document_pages")
    assert document_pages["payload"]["pages"][1]["page_number"] == 2
    archive_bundle = next(artifact for artifact in result["artifacts"] if artifact["artifact_type"] == "archive_bundle")
    assert archive_bundle["payload"]["entry_count"] == 2
    assert archive_bundle["payload"]["format"] == "zip"


def test_workspace_tool_results_promote_to_run_artifacts():
    tree_artifacts = build_artifacts_from_tool_result(
        {
            "workspace_root": "/workspace",
            "path": ".",
            "entries": [
                {"path": "src", "type": "directory", "depth": 1},
                {"path": "src/app.py", "type": "file", "depth": 2, "size_bytes": 12},
            ],
            "truncated": False,
        },
        tool_name="workspace_tree",
        tool_kind="workspace",
        step_id="step-1",
        tool_call_id="tool-1",
    )
    assert tree_artifacts[0]["artifact_type"] == "directory_tree"
    assert tree_artifacts[0]["metadata"]["workspace_root"] == "/workspace"

    read_artifacts = build_artifacts_from_tool_result(
        {"path": "src/app.py", "content": "print('ok')\n", "size_bytes": 12, "truncated": False},
        tool_name="workspace_read_file",
        tool_kind="workspace",
        step_id="step-1",
        tool_call_id="tool-1",
    )
    assert read_artifacts[0]["artifact_type"] == "code_files"
    assert read_artifacts[0]["payload"]["files"][0]["path"] == "src/app.py"

    search_artifacts = build_artifacts_from_tool_result(
        {
            "query": "needle",
            "matches": [{"path": "src/app.py", "line": 2, "preview": "needle here"}],
            "truncated": False,
        },
        tool_name="workspace_search_text",
        tool_kind="workspace",
        step_id="step-1",
        tool_call_id="tool-1",
    )
    assert search_artifacts[0]["artifact_type"] == "document_excerpt"
    assert search_artifacts[0]["payload"]["items"][0]["source"] == "src/app.py"

    info_artifacts = build_artifacts_from_tool_result(
        {
            "path": "src/app.py",
            "type": "file",
            "size_bytes": 12,
            "extension": ".py",
            "sha256": "abc",
        },
        tool_name="workspace_file_info",
        tool_kind="workspace",
        step_id="step-1",
        tool_call_id="tool-1",
    )
    assert info_artifacts[0]["artifact_type"] == "file_bundle"
    assert info_artifacts[0]["payload"]["files"][0]["metadata"]["sha256"] == "abc"


def test_workspace_status_tool_result_promotes_workspace_summary_artifact():
    artifacts = build_artifacts_from_tool_result(
        {
            "workspace": {
                "id": "tenant/run",
                "root": "/workspace",
                "status": "ready",
                "source": {"type": "upload_bundle", "bundle_ids": ["bundle-1"]},
                "snapshot": {
                    "file_count": 2,
                    "total_size_bytes": 42,
                    "snapshot_at": "2026-05-13T00:00:00+00:00",
                },
            }
        },
        tool_name="workspace_status",
        tool_kind="workspace",
        step_id="step-1",
        tool_call_id="tool-1",
    )

    assert artifacts[0]["artifact_type"] == "workspace_summary"
    assert artifacts[0]["payload"]["source"]["type"] == "upload_bundle"


def test_runtime_artifact_model_accepts_workspace_and_execution_surface_artifacts():
    for artifact_type in ("workspace_summary", "code_patch", "verification_report"):
        artifact = AgentArtifact.model_validate(
            {
                "artifact_type": artifact_type,
                "name": artifact_type,
                "payload": {},
            }
        )

        assert artifact.artifact_type == artifact_type


def test_git_tool_results_promote_to_document_excerpt_artifact():
    artifacts = build_artifacts_from_tool_result(
        {
            "command": ["git", "diff"],
            "exit_code": 0,
            "stdout": "diff --git a/app.py b/app.py\n",
            "stderr": "",
            "truncated": False,
        },
        tool_name="git_diff",
        tool_kind="workspace",
        step_id="step-1",
        tool_call_id="tool-1",
    )

    assert artifacts[0]["artifact_type"] == "document_excerpt"
    assert artifacts[0]["payload"]["items"][0]["source"] == "git"

    empty_artifacts = build_artifacts_from_tool_result(
        {
            "command": ["git", "diff"],
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
            "truncated": False,
        },
        tool_name="git_diff",
        tool_kind="workspace",
        step_id="step-1",
        tool_call_id="tool-1",
    )
    assert empty_artifacts[0]["payload"]["items"][0]["text"] == "No changes."


def test_sandbox_exec_tool_results_promote_to_verification_report_artifact():
    artifacts = build_artifacts_from_tool_result(
        {
            "status": "failed",
            "exit_code": 1,
            "command": ["python", "-m", "pytest"],
            "cwd": ".",
            "duration_ms": 123,
            "timeout_seconds": 300,
            "purpose": "test",
            "failure_category": "non_zero_exit",
            "stdout": "FAILED tests/test_app.py::test_app",
            "stderr": "",
            "truncated": False,
            "runner": {"backend": "docker", "image": "python:3.12-slim"},
            "structured_report": {
                "schema_version": "verification_report.v1",
                "summary": {"report_count": 1},
                "reports": [
                    {
                        "kind": "test",
                        "format": "pytest_text",
                        "summary": {"failed": 1},
                        "failures": [{"title": "tests/test_app.py::test_app", "severity": "error"}],
                    }
                ],
            },
        },
        tool_name="run_tests",
        tool_kind="sandbox-exec",
        step_id="step-1",
        tool_call_id="tool-1",
    )

    assert artifacts[0]["artifact_type"] == "verification_report"
    assert artifacts[0]["name"] == "run_tests - Test Verification"
    assert artifacts[0]["payload"]["kind"] == "test"
    assert artifacts[0]["payload"]["status"] == "failed"
    assert artifacts[0]["payload"]["exit_code"] == 1
    assert artifacts[0]["payload"]["summary"] == "Verification failed (non_zero_exit)."
    assert artifacts[0]["payload"]["logs"]["stdout"] == "FAILED tests/test_app.py::test_app"
    assert artifacts[0]["payload"]["runner"]["backend"] == "docker"
    assert artifacts[0]["payload"]["structured_report"]["schema_version"] == "verification_report.v1"
    assert artifacts[0]["payload"]["structured_report"]["reports"][0]["summary"]["failed"] == 1
    assert artifacts[0]["metadata"]["failure_category"] == "non_zero_exit"


def test_browser_snapshot_tool_result_promotes_to_document_excerpt_artifact():
    artifacts = build_artifacts_from_tool_result(
        {
            "status": "completed",
            "session_id": "browser-session-1",
            "url": "https://app.example.com/dashboard",
            "title": "Dashboard",
            "text": "Ready",
            "captured_at": "2026-05-14T00:00:00+00:00",
            "viewport": {"width": 1280, "height": 720},
            "source": "browser_snapshot",
        },
        tool_name="browser_snapshot",
        tool_kind="web",
        step_id="step-browser",
        tool_call_id="tool-browser",
    )

    assert artifacts[0]["artifact_type"] == "document_excerpt"
    assert artifacts[0]["name"] == "browser_snapshot - Dashboard"
    assert artifacts[0]["payload"]["items"][0]["text"] == "Ready"
    assert artifacts[0]["payload"]["items"][0]["metadata"]["session_id"] == "browser-session-1"
    assert artifacts[0]["metadata"]["url"] == "https://app.example.com/dashboard"


def test_browser_verify_tool_result_promotes_to_verification_report_artifact():
    artifacts = build_artifacts_from_tool_result(
        {
            "status": "completed",
            "session_id": "browser-session-1",
            "url": "https://app.example.com/dashboard",
            "title": "Dashboard",
            "text": "Ready",
            "console_messages": [
                {"type": "console", "level": "error", "text": "boom", "timestamp": "2026-05-16T00:00:00+00:00"}
            ],
            "network_errors": [
                {"url": "https://app.example.com/api", "method": "GET", "text": "failed", "timestamp": "2026-05-16T00:00:00+00:00"}
            ],
            "kind": "browser_verify",
            "summary": "Browser verification completed.",
            "structured_report": {
                "schema_version": "verification_report.v1",
                "reports": [
                    {
                        "kind": "browser_verify",
                        "format": "browser_diagnostics",
                        "summary": {"finding_count": 2},
                        "findings": [
                            {"title": "boom", "severity": "error"},
                            {"title": "failed", "severity": "error"},
                        ],
                    }
                ],
            },
            "source": "browser_verify",
        },
        tool_name="browser_verify",
        tool_kind="web",
        step_id="step-browser",
        tool_call_id="tool-browser",
    )

    assert artifacts[0]["artifact_type"] == "verification_report"
    assert artifacts[0]["name"] == "browser_verify - Browser Verification"
    assert artifacts[0]["payload"]["kind"] == "browser_verify"
    assert artifacts[0]["payload"]["structured_report"]["reports"][0]["kind"] == "browser_verify"
    assert artifacts[0]["metadata"]["session_id"] == "browser-session-1"


def test_browser_screenshot_tool_result_promotes_to_media_gallery_artifact():
    artifacts = build_artifacts_from_tool_result(
        {
            "status": "completed",
            "session_id": "browser-session-1",
            "url": "https://app.example.com/dashboard",
            "title": "Dashboard",
            "captured_at": "2026-05-14T00:00:00+00:00",
            "images": [
                {
                    "title": "Dashboard",
                    "path": "browser-session-1.png",
                    "mime_type": "image/png",
                    "data": "iVBORw0K",
                    "size_bytes": 6,
                }
            ],
        },
        tool_name="browser_screenshot",
        tool_kind="web",
        step_id="step-browser",
        tool_call_id="tool-browser",
    )

    assert artifacts[0]["artifact_type"] == "media_gallery"
    assert artifacts[0]["payload"]["items"][0]["mime_type"] == "image/png"
    assert artifacts[0]["payload"]["items"][0]["uri"].startswith("data:image/png;base64,")
    assert artifacts[0]["metadata"]["session_id"] == "browser-session-1"


def test_pdf_extract_tool_result_promotes_to_document_pages_artifact():
    artifacts = build_artifacts_from_tool_result(
        {
            "status": 200,
            "url": "https://files.example.com/guide.pdf",
            "requested_url": "https://files.example.com/guide.pdf",
            "filename": "guide.pdf",
            "page_count": 1,
            "extracted_pages": 1,
            "pages": [
                {
                    "page_number": 1,
                    "text": "PDF text",
                    "source": "https://files.example.com/guide.pdf",
                }
            ],
        },
        tool_name="pdf_extract",
        tool_kind="web",
        step_id="step-pdf",
        tool_call_id="tool-pdf",
    )

    assert artifacts[0]["artifact_type"] == "document_pages"
    assert artifacts[0]["name"] == "pdf_extract - guide.pdf"
    assert artifacts[0]["payload"]["pages"][0]["text"] == "PDF text"
    assert artifacts[0]["payload"]["page_count"] == 1
    assert artifacts[0]["metadata"]["status"] == 200


def test_specialized_verification_tool_results_promote_to_verification_report_artifact():
    artifacts = build_artifacts_from_tool_result(
        {
            "status": "completed",
            "exit_code": 0,
            "command": ["python", "-m", "pyright", "."],
            "cwd": ".",
            "duration_ms": 42,
            "timeout_seconds": 300,
            "purpose": "typecheck",
            "stdout": "0 errors",
            "stderr": "",
            "truncated": False,
            "ecosystem": "python",
            "report_format": "plain_text",
        },
        tool_name="typecheck_run",
        tool_kind="sandbox-exec",
        step_id="step-1",
        tool_call_id="tool-typecheck",
    )

    assert artifacts[0]["artifact_type"] == "verification_report"
    assert artifacts[0]["name"] == "typecheck_run - Typecheck Verification"
    assert artifacts[0]["payload"]["kind"] == "typecheck"
    assert artifacts[0]["payload"]["status"] == "completed"
    assert artifacts[0]["payload"]["ecosystem"] == "python"
    assert artifacts[0]["payload"]["report_format"] == "plain_text"


def test_web_tool_results_promote_to_citation_and_excerpt_artifacts():
    search_artifacts = build_artifacts_from_tool_result(
        {
            "query": "runtime",
            "items": [
                {
                    "title": "Runtime Plan",
                    "url": "https://docs.example.com/runtime",
                    "snippet": "Use structured web artifacts.",
                }
            ],
            "fetched_at": "2026-05-14T00:00:00+00:00",
            "source": "web_search",
        },
        tool_name="web_search",
        tool_kind="web",
        step_id="step-1",
        tool_call_id="tool-web-1",
    )

    assert search_artifacts[0]["artifact_type"] == "citations"
    assert search_artifacts[0]["payload"]["items"][0]["url"] == "https://docs.example.com/runtime"
    assert search_artifacts[0]["metadata"]["query"] == "runtime"

    page_artifacts = build_artifacts_from_tool_result(
        {
            "url": "https://docs.example.com/runtime",
            "requested_url": "https://docs.example.com/runtime",
            "status": 200,
            "title": "Runtime Plan",
            "text": "Use structured web artifacts.",
            "fetched_at": "2026-05-14T00:00:00+00:00",
            "truncated": False,
        },
        tool_name="open_page",
        tool_kind="web",
        step_id="step-1",
        tool_call_id="tool-web-2",
    )

    assert page_artifacts[0]["artifact_type"] == "document_excerpt"
    assert page_artifacts[0]["payload"]["items"][0]["source"] == "https://docs.example.com/runtime"
    assert page_artifacts[0]["payload"]["items"][0]["metadata"]["status"] == 200

    download_artifacts = build_artifacts_from_tool_result(
        {
            "url": "https://docs.example.com/runtime.pdf",
            "requested_url": "https://docs.example.com/runtime.pdf",
            "status": 200,
            "filename": "runtime.pdf",
            "content_type": "application/pdf",
            "bytes": 12,
            "sha256": "hash",
            "truncated": False,
            "files": [
                {
                    "name": "runtime.pdf",
                    "path": "runtime.pdf",
                    "mime_type": "application/pdf",
                    "size_bytes": 12,
                    "data": "ZmFrZSBwZGY=",
                    "source_url": "https://docs.example.com/runtime.pdf",
                    "metadata": {"sha256": "hash"},
                }
            ],
        },
        tool_name="download_file",
        tool_kind="web",
        step_id="step-1",
        tool_call_id="tool-web-3",
    )

    assert download_artifacts[0]["artifact_type"] == "file_bundle"
    assert download_artifacts[0]["payload"]["files"][0]["name"] == "runtime.pdf"
    assert download_artifacts[0]["payload"]["files"][0]["uri"].startswith("data:application/pdf;base64,")
    assert download_artifacts[0]["payload"]["files"][0]["source"] == "https://docs.example.com/runtime.pdf"
    assert download_artifacts[0]["metadata"]["sha256"] == "hash"


def test_build_artifacts_from_tool_result_merges_structured_content_with_code_resources():
    artifacts = build_artifacts_from_tool_result(
        {
            "structured_content": {
                "citations": [
                    {
                        "title": "Runtime Plan",
                        "url": "https://example.com/runtime-plan",
                    }
                ]
            },
            "content": [
                {
                    "type": "resource",
                    "resource": {
                        "name": "agent_runtime.py",
                        "uri": "file:///workspace/agent_runtime.py",
                        "mimeType": "text/x-python",
                        "text": "print('hello')\n",
                    },
                }
            ],
        },
        tool_name="inspect_workspace",
        tool_kind="mcp",
        step_id="step-2",
        tool_call_id="tool-call-2",
        include_answer=False,
    )

    artifact_types = [artifact["artifact_type"] for artifact in artifacts]
    assert "citations" in artifact_types
    assert "code_files" in artifact_types
    code_files = next(artifact for artifact in artifacts if artifact["artifact_type"] == "code_files")
    assert code_files["payload"]["files"][0]["path"] == "agent_runtime.py"
    assert code_files["payload"]["files"][0]["language"] == "python"


def test_build_artifacts_from_tool_result_promotes_media_and_file_resources_from_content():
    artifacts = build_artifacts_from_tool_result(
        {
            "content": [
                {
                    "type": "image",
                    "mimeType": "image/png",
                    "data": "ZmFrZS1wbmc=",
                    "title": "Runtime Diagram",
                },
                {
                    "type": "resource",
                    "resource": {
                        "name": "catalog-export.pdf",
                        "uri": "https://example.com/catalog-export.pdf",
                        "mimeType": "application/pdf",
                    },
                },
            ]
        },
        tool_name="inspect_catalog",
        tool_kind="mcp",
        step_id="step-4",
        tool_call_id="tool-call-4",
        include_answer=False,
    )

    artifact_types = [artifact["artifact_type"] for artifact in artifacts]
    assert "media_gallery" in artifact_types
    assert "file_bundle" in artifact_types
    media = next(artifact for artifact in artifacts if artifact["artifact_type"] == "media_gallery")
    assert media["payload"]["items"][0]["uri"].startswith("data:image/png;base64,")
    bundle = next(artifact for artifact in artifacts if artifact["artifact_type"] == "file_bundle")
    assert bundle["payload"]["files"][0]["uri"] == "https://example.com/catalog-export.pdf"


def test_build_artifacts_from_tool_result_promotes_embedded_directory_document_and_archive_resources():
    artifacts = build_artifacts_from_tool_result(
        {
            "content": [
                {
                    "type": "resource",
                    "resource": {
                        "name": "workspace",
                        "children": [
                            {"path": "src/agent_runtime.py", "type": "file"},
                            {"path": "tests/", "type": "directory"},
                        ],
                    },
                },
                {
                    "type": "resource",
                    "resource": {
                        "name": "catalog-export.pdf",
                        "pages": [
                            {"page": 1, "text": "Summary page"},
                            {"page": 2, "text": "Tool details"},
                        ],
                    },
                },
                {
                    "type": "resource",
                    "resource": {
                        "name": "workspace-export.zip",
                        "format": "zip",
                        "entries": [
                            {"path": "src/agent_runtime.py", "size_bytes": 1024, "compressed_size_bytes": 256},
                        ],
                    },
                },
            ]
        },
        tool_name="inspect_workspace",
        tool_kind="mcp",
        step_id="step-5",
        tool_call_id="tool-call-5",
        include_answer=False,
    )

    artifact_types = [artifact["artifact_type"] for artifact in artifacts]
    assert "directory_tree" in artifact_types
    assert "document_pages" in artifact_types
    assert "archive_bundle" in artifact_types
    assert all(artifact["metadata"]["tool_call_id"] == "tool-call-5" for artifact in artifacts)


def test_build_artifacts_from_tool_result_supports_single_content_object_with_resource_link_metadata():
    artifacts = build_artifacts_from_tool_result(
        {
            "content": {
                "type": "resource",
                "title": "Catalog Snapshot",
                "resource_link": "https://example.com/catalog/snapshot.json",
                "mimeType": "application/json",
                "text": '{"status":"ready"}',
                "annotations": {"audience": ["admin"]},
                "_meta": {"origin": "catalog-refresh"},
            }
        },
        tool_name="inspect_catalog",
        tool_kind="mcp",
        step_id="step-6",
        tool_call_id="tool-call-6",
        include_answer=False,
    )

    code_files = next(artifact for artifact in artifacts if artifact["artifact_type"] == "code_files")
    file_entry = code_files["payload"]["files"][0]
    assert file_entry["metadata"]["source"] == "https://example.com/catalog/snapshot.json"
    assert file_entry["metadata"]["annotations"]["audience"] == ["admin"]
    assert file_entry["metadata"]["_meta"]["origin"] == "catalog-refresh"


def test_build_artifacts_from_tool_result_promotes_nested_structured_content_from_mcp_entries():
    artifacts = build_artifacts_from_tool_result(
        {
            "content": [
                {
                    "type": "resource",
                    "title": "Preview",
                    "resourceLink": "https://example.com/review/preview",
                    "structuredContent": {
                        "review_findings": [
                            {
                                "title": "Catalog drift",
                                "severity": "medium",
                                "description": "Tool output still exposes stale entries after refresh.",
                            }
                        ],
                        "task_plan": {
                            "summary": "Tighten refresh path",
                            "steps": [{"title": "Invalidate stale catalog", "status": "pending"}],
                        },
                    },
                    "annotations": {"phase": "post-refresh"},
                }
            ]
        },
        tool_name="review_catalog",
        tool_kind="mcp",
        step_id="step-7",
        tool_call_id="tool-call-7",
        include_answer=False,
    )

    artifact_types = [artifact["artifact_type"] for artifact in artifacts]
    assert "review_findings" in artifact_types
    assert "task_plan" in artifact_types
    findings = next(artifact for artifact in artifacts if artifact["artifact_type"] == "review_findings")
    assert findings["metadata"]["content_metadata"]["annotations"]["phase"] == "post-refresh"
    assert findings["metadata"]["content_metadata"]["resourceLink"] == "https://example.com/review/preview"


def test_build_artifacts_from_tool_result_parses_json_content_items_into_structured_artifacts():
    artifacts = build_artifacts_from_tool_result(
        {
            "content": [
                {
                    "type": "text",
                    "text": """
                    {
                      "review_findings": [
                        {
                          "title": "Missing resume reset",
                          "severity": "high",
                          "description": "Old tool artifacts leak into the new attempt."
                        }
                      ],
                      "task_plan": {
                        "summary": "Tighten resume behavior",
                        "steps": [
                          {"title": "Reset execution context", "status": "completed"},
                          {"title": "Add regression coverage", "status": "pending"}
                        ]
                      }
                    }
                    """,
                }
            ]
        },
        tool_name="analyze_run",
        tool_kind="mcp",
        step_id="step-3",
        tool_call_id="tool-call-3",
        include_answer=False,
    )

    artifact_types = [artifact["artifact_type"] for artifact in artifacts]
    assert "review_findings" in artifact_types
    assert "task_plan" in artifact_types


def test_hydrate_legacy_result_preserves_richer_artifact_contract_from_final_output_json():
    result = hydrate_legacy_result(
        final_output=None,
        final_output_text=None,
        final_output_json={
            "document_pages": {
                "title": "Deployment Checklist",
                "pages": [
                    {"page": 1, "text": "Validate schema migrations."},
                    {"page": 2, "text": "Verify workspace hydration."},
                ],
            },
            "archive_bundle": {
                "name": "release-bundle.zip",
                "format": "zip",
                "entries": [
                    {"path": "dist/app.js", "size_bytes": 2048, "compressed_size_bytes": 512},
                ],
            },
        },
        artifacts=[],
    )

    artifact_types = [artifact["artifact_type"] for artifact in result["artifacts"]]
    assert "document_pages" in artifact_types
    assert "archive_bundle" in artifact_types
    assert result["final_output_text"] == "Validate schema migrations."


def test_merge_artifacts_deduplicates_repeated_payloads():
    artifacts = merge_artifacts(
        [
            {
                "artifact_type": "document_excerpt",
                "name": "search_docs - Preview",
                "payload": {"items": [{"title": "Result", "text": "same", "source": ""}]},
            }
        ],
        [
            {
                "artifact_type": "document_excerpt",
                "name": "search_docs - Preview",
                "payload": {"items": [{"title": "Result", "text": "same", "source": ""}]},
            }
        ],
    )

    assert len(artifacts) == 1
    assert artifacts[0]["artifact_type"] == "document_excerpt"


def test_merge_artifacts_deduplicates_same_payload_even_if_names_differ():
    artifacts = merge_artifacts(
        [
            {
                "artifact_type": "citations",
                "name": "Runtime Sources",
                "payload": {"items": [{"title": "Runtime Plan", "url": "https://example.com/runtime-plan"}]},
            }
        ],
        [
            {
                "artifact_type": "citations",
                "name": "Citations",
                "payload": {"items": [{"title": "Runtime Plan", "url": "https://example.com/runtime-plan"}]},
            }
        ],
    )

    assert len(artifacts) == 1
    assert artifacts[0]["name"] == "Runtime Sources"
