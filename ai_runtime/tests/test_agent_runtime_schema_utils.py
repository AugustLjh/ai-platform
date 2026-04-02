from core.agent_runtime.schema_utils import merge_output_schema, normalize_output_schema


def test_normalize_output_schema_merges_anyof_object_variants():
    schema = normalize_output_schema(
        {
            "anyOf": [
                {
                    "type": "object",
                    "required": ["answer"],
                    "properties": {
                        "answer": {"type": "string"},
                        "status": {"type": "string", "enum": ["done", "blocked"]},
                    },
                },
                {
                    "type": "object",
                    "required": ["task_plan"],
                    "properties": {
                        "task_plan": {
                            "type": "object",
                            "properties": {
                                "steps": {"type": "array", "items": {"type": "string"}},
                            },
                        }
                    },
                },
            ]
        }
    )

    assert schema["type"] == "object"
    assert schema["required"] == ["answer", "task_plan"]
    assert schema["properties"]["answer"]["type"] == "string"
    assert schema["properties"]["task_plan"]["type"] == "object"
    assert schema["properties"]["status"]["enum"] == ["done", "blocked"]


def test_merge_output_schema_merges_additional_properties_schema_and_constraints():
    schema = merge_output_schema(
        {
            "type": "object",
            "properties": {
                "metrics": {
                    "type": "object",
                    "additionalProperties": {"type": "integer", "minimum": 0},
                }
            },
        },
        {
            "type": "object",
            "properties": {
                "metrics": {
                    "type": "object",
                    "additionalProperties": {"type": "integer", "maximum": 10},
                }
            },
        },
    )

    metrics_schema = schema["properties"]["metrics"]["additionalProperties"]
    assert metrics_schema["type"] == "integer"
    assert metrics_schema["minimum"] == 0
    assert metrics_schema["maximum"] == 10
