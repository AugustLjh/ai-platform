from __future__ import annotations

import re
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
    "credential",
    "credentials",
    "refresh_token",
    "private_key",
    "ssh_key",
    "jwt",
    "bearer",
)
SENSITIVE_CONTAINERS = {"env", "headers", "credentials", "auth"}
SENSITIVE_TEXT_PATTERNS = (
    re.compile(
        r"(?i)\b(authorization\s*[:=]\s*bearer\s+)([A-Za-z0-9._~+/=-]{8,})"
    ),
    re.compile(r"(?i)\b(bearer\s+)([A-Za-z0-9._~+/=-]{16,})"),
    re.compile(
        r"(?i)\b((?:api[_-]?key|access[_-]?key|secret|token|password|passwd|client[_-]?secret)\s*[:=]\s*)(\"[^\"]+\"|'[^']+'|[^\s,;]+)"
    ),
    re.compile(r"\b(sk-[A-Za-z0-9]{10,})\b"),
    re.compile(r"\b(AKIA[0-9A-Z]{12,})\b"),
)


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower().strip()
    return any(token in lowered for token in SENSITIVE_TOKENS)


def _redact_text(value: str) -> str:
    redacted = value
    for pattern in SENSITIVE_TEXT_PATTERNS:
        if pattern.groups >= 2:
            redacted = pattern.sub(lambda match: f"{match.group(1)}{MASK}", redacted)
        else:
            redacted = pattern.sub(MASK, redacted)
    return redacted


def sanitize_runtime_payload(value: Any, path: tuple[str, ...] = ()) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): sanitize_runtime_payload(
                item,
                path + (str(key),),
            )
            for key, item in value.items()
        }

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if path and path[-1].lower() in SENSITIVE_CONTAINERS:
            return [MASK for _ in value]
        return [sanitize_runtime_payload(item, path) for item in value]

    if not isinstance(value, str):
        return value

    if path:
        current = path[-1].lower()
        parent = path[-2].lower() if len(path) > 1 else ""
        if _is_sensitive_key(current) or current in SENSITIVE_CONTAINERS or parent in SENSITIVE_CONTAINERS:
            return MASK if value else value
    return _redact_text(value)


def build_event_payload(**payload: Any) -> Dict[str, Any]:
    sanitized = sanitize_runtime_payload(payload)
    return sanitized if isinstance(sanitized, dict) else {}
