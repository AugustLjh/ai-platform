from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict


def _ensure_schema_type(schema: Dict[str, Any]) -> Dict[str, Any]:
    normalized = deepcopy(schema)
    if "type" not in normalized:
        if isinstance(normalized.get("properties"), dict) or isinstance(normalized.get("required"), list):
            normalized["type"] = "object"
        elif "items" in normalized:
            normalized["type"] = "array"
    return normalized


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
    elif incoming_additional is not None:
        merged["additionalProperties"] = deepcopy(incoming_additional)

    return merged


def _merge_array_schema(base: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(base)
    merged.setdefault("type", "array")
    base_items = merged.get("items")
    incoming_items = incoming.get("items")
    if isinstance(base_items, dict) and isinstance(incoming_items, dict):
        merged["items"] = merge_output_schema(base_items, incoming_items)
    elif isinstance(incoming_items, dict):
        merged["items"] = deepcopy(incoming_items)
    return merged


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
    return merged


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
            for option in options:
                candidate = normalize_output_schema(option if isinstance(option, dict) else {})
                if candidate:
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

    return normalized
