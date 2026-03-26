from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


def encode_json(value: Any, fallback: Any) -> str:
    if value is None:
        payload = fallback
    elif isinstance(value, Mapping):
        payload = dict(value)
    elif isinstance(value, list):
        payload = list(value)
    else:
        payload = value
    return json.dumps(payload, ensure_ascii=False)


def parse_json_field(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return fallback
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return fallback
    return fallback
