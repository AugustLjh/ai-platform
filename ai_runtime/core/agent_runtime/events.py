from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Dict


MASK = "********"
SENSITIVE_TOKENS = (
    "secret",
    "password",
    "passwd",
    "token",
    "api_key",
    "apikey",
    "access_key",
    "authorization",
    "cookie",
    "client_secret",
    "private_key",
    "bearer",
)
SENSITIVE_CONTAINERS = {"env", "headers", "credentials", "auth"}


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower().strip()
    return any(token in lowered for token in SENSITIVE_TOKENS)


def _sanitize(value: Any, path: tuple[str, ...] = ()) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _sanitize(
                item,
                path + (str(key),),
            )
            for key, item in value.items()
        }

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if path and path[-1].lower() in SENSITIVE_CONTAINERS:
            return [MASK for _ in value]
        return [_sanitize(item, path) for item in value]

    if not isinstance(value, str):
        return value

    if path:
        current = path[-1].lower()
        parent = path[-2].lower() if len(path) > 1 else ""
        if _is_sensitive_key(current) or current in SENSITIVE_CONTAINERS or parent in SENSITIVE_CONTAINERS:
            return MASK if value else value
    return value


def build_event_payload(**payload: Any) -> Dict[str, Any]:
    return _sanitize(payload)
