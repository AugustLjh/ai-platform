from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


_MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "core"
    / "agent_runtime"
    / "repositories"
    / "json_utils.py"
)
_SPEC = spec_from_file_location("agent_runtime_json_utils", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

encode_json = _MODULE.encode_json
parse_json_field = _MODULE.parse_json_field


def test_encode_json_serializes_mappings_and_lists():
    assert encode_json({"message": "现在几点"}, {}) == '{"message": "现在几点"}'
    assert encode_json(["a", "b"], []) == '["a", "b"]'


def test_parse_json_field_handles_strings_and_fallbacks():
    assert parse_json_field('{"message": "现在几点"}', {}) == {"message": "现在几点"}
    assert parse_json_field("", {}) == {}
    assert parse_json_field(None, []) == []
