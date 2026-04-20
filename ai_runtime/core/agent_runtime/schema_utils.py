from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict


STRUCTURAL_SCHEMA_KEYS = {"type", "properties", "required", "items", "additionalProperties", "allOf", "anyOf", "oneOf"}


def _normalize_schema_type(schema_type: Any) -> Any:
    if isinstance(schema_type, list):
        candidates = [item for item in schema_type if isinstance(item, str) and item != "null"]
        if len(candidates) == 1:
            return candidates[0]
        if candidates:
            return candidates[0]
        null_candidates = [item for item in schema_type if isinstance(item, str)]
        if len(null_candidates) == 1:
            return null_candidates[0]
    return schema_type


def _ensure_schema_type(schema: Dict[str, Any]) -> Dict[str, Any]:
    normalized = deepcopy(schema)
    normalized_type = _normalize_schema_type(normalized.get("type"))
    if normalized_type is not None:
        normalized["type"] = normalized_type
    if "type" not in normalized:
        if isinstance(normalized.get("properties"), dict) or isinstance(normalized.get("required"), list):
            normalized["type"] = "object"
        elif "items" in normalized:
            normalized["type"] = "array"
    return normalized


def _merge_known_constraint(key: str, left: Any, right: Any) -> Any:
    if key == "enum" and isinstance(left, list) and isinstance(right, list):
        merged = []
        for item in list(left) + list(right):
            if item not in merged:
                merged.append(deepcopy(item))
        return merged

    if key in {"minItems", "minimum", "minLength"} and isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return max(left, right)

    if key in {"maxItems", "maximum", "maxLength"} and isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return min(left, right)

    if key == "examples" and isinstance(left, list) and isinstance(right, list):
        merged = []
        for item in list(left) + list(right):
            if item not in merged:
                merged.append(deepcopy(item))
        return merged

    return deepcopy(right)


def _merge_schema_metadata(merged: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    passthrough_keys = {
        "title",
        "description",
        "default",
        "enum",
        "const",
        "examples",
        "minItems",
        "maxItems",
        "minimum",
        "maximum",
        "minLength",
        "maxLength",
        "pattern",
        "uniqueItems",
    }
    for key, value in incoming.items():
        if key in STRUCTURAL_SCHEMA_KEYS or value is None:
            continue
        if key not in passthrough_keys and key in merged:
            continue
        if key in merged:
            merged[key] = _merge_known_constraint(key, merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _merge_object_schema(base: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(base)
    merged.setdefault("type", "object")

    base_properties = merged.get("properties") if isinstance(merged.get("properties"), dict) else {}
    incoming_properties = incoming.get("properties") if isinstance(incoming.get("properties"), dict) else {}
    if base_properties or incoming_properties:
        merged_properties: Dict[str, Any] = {}
        ordered_keys = list(base_properties.keys()) + [key for key in incoming_properties.keys() if key not in base_properties]
        for key in ordered_keys:
            left = base_properties.get(key)
            right = incoming_properties.get(key)
            if isinstance(left, dict) and isinstance(right, dict):
                merged_properties[key] = merge_output_schema(left, right)
            elif isinstance(left, dict):
                merged_properties[key] = deepcopy(left)
            elif isinstance(right, dict):
                merged_properties[key] = deepcopy(right)
        merged["properties"] = merged_properties

    required = []
    for item in list(merged.get("required") or []) + list(incoming.get("required") or []):
        if item not in required:
            required.append(item)
    if required:
        merged["required"] = required

    base_additional = merged.get("additionalProperties")
    incoming_additional = incoming.get("additionalProperties")
    if isinstance(base_additional, bool) and isinstance(incoming_additional, bool):
        merged["additionalProperties"] = base_additional and incoming_additional
    elif isinstance(base_additional, dict) and isinstance(incoming_additional, dict):
        merged["additionalProperties"] = merge_output_schema(base_additional, incoming_additional)
    elif base_additional is False or incoming_additional is False:
        merged["additionalProperties"] = False
    elif isinstance(base_additional, dict) and incoming_additional is True:
        merged["additionalProperties"] = deepcopy(base_additional)
    elif base_additional is True and isinstance(incoming_additional, dict):
        merged["additionalProperties"] = deepcopy(incoming_additional)
    elif incoming_additional is not None:
        merged["additionalProperties"] = deepcopy(incoming_additional)

    return _merge_schema_metadata(merged, incoming)


def _merge_array_schema(base: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(base)
    merged.setdefault("type", "array")
    base_items = merged.get("items")
    incoming_items = incoming.get("items")
    if isinstance(base_items, dict) and isinstance(incoming_items, dict):
        merged["items"] = merge_output_schema(base_items, incoming_items)
    elif isinstance(incoming_items, dict):
        merged["items"] = deepcopy(incoming_items)
    return _merge_schema_metadata(merged, incoming)


def _schema_strength(schema: Dict[str, Any]) -> int:
    schema_type = schema.get("type")
    score = 0

    if schema_type == "object":
        properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        score += 10 + len(properties) * 4 + len(schema.get("required") or []) * 3
        for prop in properties.values():
            if isinstance(prop, dict):
                score += _schema_strength(prop)
    elif schema_type == "array":
        score += 8 + len(schema.get("required") or []) * 2
        if isinstance(schema.get("items"), dict):
            score += _schema_strength(schema["items"])
    else:
        score += 2

    if isinstance(schema.get("enum"), list):
        score += len(schema["enum"])
    if "const" in schema:
        score += 2
    if "default" in schema:
        score += 1
    return score


def merge_output_schema(base: Dict[str, Any] | None, incoming: Dict[str, Any] | None) -> Dict[str, Any]:
    left = normalize_output_schema(base)
    right = normalize_output_schema(incoming)

    if not left:
        return right
    if not right:
        return left

    left_type = left.get("type")
    right_type = right.get("type")
    if left_type == "object" and right_type == "object":
        return _merge_object_schema(left, right)
    if left_type == "array" and right_type == "array":
        return _merge_array_schema(left, right)

    merged = deepcopy(left)
    for key, value in right.items():
        if key not in merged:
            merged[key] = deepcopy(value)
    return _merge_schema_metadata(merged, right)


def normalize_output_schema(schema: Dict[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(schema, dict):
        return {}

    normalized = _ensure_schema_type(schema)

    all_of = normalized.get("allOf")
    if isinstance(all_of, list) and all_of:
        merged: Dict[str, Any] = {}
        for item in all_of:
            if isinstance(item, dict):
                merged = merge_output_schema(merged, item)

        remainder = {key: value for key, value in normalized.items() if key != "allOf"}
        return merge_output_schema(merged, remainder)

    for key in ("anyOf", "oneOf"):
        options = normalized.get(key)
        if isinstance(options, list) and options:
            normalized_options = [
                normalize_output_schema(option if isinstance(option, dict) else {})
                for option in options
            ]
            normalized_options = [candidate for candidate in normalized_options if candidate]
            if normalized_options:
                option_types = {candidate.get("type") for candidate in normalized_options if candidate.get("type")}
                if len(option_types) == 1 and option_types <= {"object", "array"}:
                    candidate: Dict[str, Any] = {}
                    for option in normalized_options:
                        candidate = merge_output_schema(candidate, option)
                else:
                    candidate = max(normalized_options, key=_schema_strength)
                remainder = {item_key: item_value for item_key, item_value in normalized.items() if item_key != key}
                return merge_output_schema(candidate, remainder)
            return {}

    if normalized.get("type") == "object":
        properties = normalized.get("properties")
        if isinstance(properties, dict):
            normalized["properties"] = {
                key: normalize_output_schema(value) if isinstance(value, dict) else value
                for key, value in properties.items()
            }
    elif normalized.get("type") == "array" and isinstance(normalized.get("items"), dict):
        normalized["items"] = normalize_output_schema(normalized["items"])

    return _merge_schema_metadata(normalized, normalized)
