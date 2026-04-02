from core.agent_runtime.result_contract import (
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
