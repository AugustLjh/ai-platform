from __future__ import annotations

import asyncio
import fnmatch
import ipaddress
import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlparse

import aiohttp

from ai_runtime.core.agent_runtime.tools.base import BaseTool, ToolContext, ToolLookupContext, ToolSpec
from ai_runtime.core.database import get_db_manager


DEFAULT_OBSERVABILITY_TOOL_NAMES = (
    "db_query_readonly",
    "redis_inspect",
    "http_health_check",
    "service_logs",
    "metrics_query",
)
DEFAULT_REDIS_COMMANDS = ("PING", "INFO", "DBSIZE", "TIME")
DEFAULT_LOG_EXTENSIONS = (".log", ".txt", ".jsonl")
DEFAULT_METRIC_ALLOWED_NAMES: tuple[str, ...] = ()
SENSITIVE_KEY_RE = re.compile(r"(password|passwd|pwd|secret|token|api[_-]?key|authorization|credential)", re.I)
SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?i)(password|passwd|pwd|secret|token|api[_-]?key|authorization)\s*[:=]\s*([^\s,;]+)"
)
SQL_BLOCKLIST_RE = re.compile(
    r"\b("
    r"insert|update|delete|merge|create|alter|drop|truncate|grant|revoke|copy|call|do|"
    r"vacuum|analyze|lock|listen|notify|execute|prepare|deallocate|set|reset|refresh|"
    r"cluster|reindex|discard"
    r")\b",
    re.I,
)
SQL_ALLOWED_PREFIX_RE = re.compile(r"^\s*(select|with|show|explain)\b", re.I)
SQL_COMMENT_RE = re.compile(r"(--|/\*)")
PROMETHEUS_METRIC_NAME_RE = re.compile(r"^[a-zA-Z_:][a-zA-Z0-9_:]*$")


def _parse_csv(value: str | None, default: Sequence[str]) -> list[str]:
    if value is None or not value.strip():
        return [item for item in default]
    return [item.strip() for item in value.split(",") if item.strip()]


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _clamp_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _tool_metadata(*, capability: str, side_effect: str = "none", risk_level: str = "medium") -> dict[str, Any]:
    return {
        "provider": "observability",
        "capability": capability,
        "access_level": "read",
        "side_effect": side_effect,
        "requires_workspace": False,
        "requires_sandbox": False,
        "risk_level": risk_level,
    }


def _redact_value(key: str, value: Any) -> Any:
    if SENSITIVE_KEY_RE.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(item_key): _redact_value(str(item_key), item_value) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_redact_value(key, item) for item in value]
    return value


def _safe_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return {str(key): _safe_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_json_value(item) for item in value]
    return str(value)


def _truncate_text(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


def _redact_text(text: str) -> str:
    return SENSITIVE_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)


def _is_loopback_or_local(host: str) -> bool:
    normalized = host.strip().lower()
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _domain_matches(host: str, patterns: Sequence[str]) -> bool:
    host = host.lower()
    for pattern in patterns:
        normalized = pattern.strip().lower()
        if not normalized:
            continue
        if normalized.startswith("*."):
            if host.endswith(normalized[1:]):
                return True
        elif host == normalized or host.endswith("." + normalized):
            return True
    return False


def _host_allowed_for_policy(raw_url: str | None, policy: "ObservabilityPolicy") -> bool:
    url = str(raw_url or "").strip()
    if not url:
        return False
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    if policy.allowed_http_domains and _domain_matches(host, policy.allowed_http_domains):
        return True
    return policy.allow_loopback_http and _is_loopback_or_local(host)


def _metric_name_allowed(name: str, patterns: Sequence[str]) -> bool:
    if not patterns:
        return True
    return any(fnmatch.fnmatchcase(name, pattern.strip()) for pattern in patterns if pattern.strip())


def build_observability_audit_report(policy: "ObservabilityPolicy", *, enabled: bool = True) -> dict[str, Any]:
    """Return a deterministic safety report for read-only observability tools."""

    available_tools = []
    if enabled and policy.db_configured:
        available_tools.append("db_query_readonly")
    if enabled and policy.redis_configured:
        available_tools.append("redis_inspect")
    if enabled and policy.log_roots:
        available_tools.append("service_logs")
    if enabled and _host_allowed_for_policy(policy.default_health_url, policy):
        available_tools.append("http_health_check")
    if enabled and _host_allowed_for_policy(policy.metrics_url, policy):
        available_tools.append("metrics_query")

    checks = [
        {
            "key": "sql_readonly_guard",
            "status": "pass" if policy.db_configured else "not_configured",
            "severity": "high",
            "summary": "SQL is restricted to single SELECT/WITH/SHOW/EXPLAIN statements with blocked mutation keywords.",
        },
        {
            "key": "sql_statement_timeout",
            "status": "pass",
            "severity": "medium",
            "summary": f"SQL statement timeout is capped at {policy.timeout_seconds}s by default.",
        },
        {
            "key": "metrics_allowlist",
            "status": "pass" if policy.allowed_metric_names else "warning",
            "severity": "medium",
            "summary": "Metrics names are constrained by allowlist patterns."
            if policy.allowed_metric_names
            else "Metrics allowlist is empty; URL policy and sample budget still apply.",
        },
        {
            "key": "metrics_budget",
            "status": "pass",
            "severity": "medium",
            "summary": f"Metrics parsing is capped at {policy.max_metric_lines} lines and {policy.max_metric_samples} samples.",
        },
        {
            "key": "http_target_policy",
            "status": "pass" if policy.allowed_http_domains or policy.allow_loopback_http else "warning",
            "severity": "medium",
            "summary": "HTTP observability targets are restricted to loopback and/or configured domains.",
        },
        {
            "key": "log_root_policy",
            "status": "pass" if policy.log_roots else "not_configured",
            "severity": "medium",
            "summary": "Service logs are restricted to configured roots and allowed extensions.",
        },
        {
            "key": "log_redaction",
            "status": "pass",
            "severity": "high",
            "summary": "Log and database outputs redact common secret, token, password and credential fields.",
        },
    ]
    warnings = [item for item in checks if item["status"] in {"warning", "not_configured"}]
    failures = [item for item in checks if item["status"] == "fail"]
    return {
        "status": "failed" if failures else "warning" if warnings else "healthy",
        "enabled": enabled,
        "available_tools": available_tools,
        "checks": checks,
        "recommendations": [
            "Use a database-side read-only role for observability queries.",
            "Configure AGENT_OBSERVABILITY_METRIC_ALLOWLIST for production metrics endpoints.",
            "Keep AGENT_OBSERVABILITY_ALLOWED_DOMAINS narrow and prefer loopback scraping for internal services.",
        ],
    }


@dataclass(frozen=True)
class ObservabilityPolicy:
    enabled_tool_names: tuple[str, ...]
    db_configured: bool = True
    redis_configured: bool = False
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_password: str | None = None
    redis_allowed_commands: tuple[str, ...] = DEFAULT_REDIS_COMMANDS
    allowed_http_domains: tuple[str, ...] = ()
    allow_loopback_http: bool = True
    default_health_url: str | None = None
    metrics_url: str | None = None
    allowed_metric_names: tuple[str, ...] = DEFAULT_METRIC_ALLOWED_NAMES
    max_metric_lines: int = 5000
    max_metric_samples: int = 500
    log_roots: tuple[Path, ...] = ()
    log_extensions: tuple[str, ...] = DEFAULT_LOG_EXTENSIONS
    max_rows: int = 100
    max_output_chars: int = 40_000
    timeout_seconds: int = 10


class ObservabilityTool(BaseTool):
    def __init__(self, policy: ObservabilityPolicy, db_pool: Any | None = None) -> None:
        self.policy = policy
        self.db_pool = db_pool

    def _truncate(self, text: str) -> tuple[str, bool]:
        return _truncate_text(text, self.policy.max_output_chars)

    def _validate_http_url(self, raw_url: Any, *, allow_empty: bool = False) -> str:
        url = str(raw_url or "").strip()
        if not url and allow_empty:
            return ""
        if not url:
            raise ValueError("url is required")
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise PermissionError("only http and https URLs are allowed")
        host = (parsed.hostname or "").lower()
        if not host:
            raise ValueError("url host is required")
        if self.policy.allowed_http_domains and _domain_matches(host, self.policy.allowed_http_domains):
            return url
        if self.policy.allow_loopback_http and _is_loopback_or_local(host):
            return url
        raise PermissionError("url host is outside the observability allowlist")

    def _resolve_log_path(self, raw_path: Any) -> Path:
        path_text = str(raw_path or "").strip()
        if not path_text:
            raise ValueError("path is required")
        candidate = Path(path_text).expanduser().resolve(strict=True)
        if not candidate.is_file():
            raise ValueError("path must refer to a file")
        if self.policy.log_extensions and candidate.suffix.lower() not in {item.lower() for item in self.policy.log_extensions}:
            raise PermissionError("log file extension is not allowed")
        for root in self.policy.log_roots:
            if candidate == root or root in candidate.parents:
                return candidate
        raise PermissionError("log path is outside configured observability log roots")


class DBQueryReadonlyTool(ObservabilityTool):
    spec = ToolSpec(
        name="db_query_readonly",
        description="Run a bounded read-only SQL query against the configured runtime database.",
        input_schema={
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 500},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 30},
            },
        },
        kind="observability",
        metadata=_tool_metadata(capability="db_readonly_query", side_effect="database"),
    )

    def _validate_query(self, query: str) -> str:
        cleaned = query.strip()
        if not cleaned:
            raise ValueError("query is required")
        if SQL_COMMENT_RE.search(cleaned):
            raise PermissionError("SQL comments are not allowed in readonly observability queries")
        if ";" in cleaned.rstrip(";"):
            raise PermissionError("multiple SQL statements are not allowed")
        cleaned = cleaned.rstrip(";").strip()
        if not SQL_ALLOWED_PREFIX_RE.match(cleaned):
            raise PermissionError("only SELECT, WITH, SHOW and EXPLAIN statements are allowed")
        if SQL_BLOCKLIST_RE.search(cleaned):
            raise PermissionError("SQL statement contains a blocked keyword")
        return cleaned

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        del context
        if not self.policy.db_configured:
            raise RuntimeError("readonly database observability is not configured")
        query = self._validate_query(str(arguments.get("query") or ""))
        limit = _clamp_int(arguments.get("limit"), default=50, minimum=1, maximum=min(500, self.policy.max_rows))
        timeout_seconds = _clamp_int(arguments.get("timeout_seconds"), default=self.policy.timeout_seconds, minimum=1, maximum=30)
        pool = self.db_pool
        if pool is None:
            pool = get_db_manager().pool

        lower_query = query.lower()
        can_wrap_limit = lower_query.startswith(("select", "with"))

        async with pool.acquire() as conn:
            async with conn.transaction(readonly=True):
                await conn.execute(f"SET LOCAL statement_timeout = {timeout_seconds * 1000}")
                if can_wrap_limit:
                    rows = await conn.fetch(f"SELECT * FROM ({query}) AS readonly_query LIMIT {limit}")
                else:
                    rows = (await conn.fetch(query))[:limit]

        items = []
        for row in rows:
            record = dict(row)
            items.append({str(key): _redact_value(str(key), _safe_json_value(value)) for key, value in record.items()})
        return {
            "status": "completed",
            "query_type": "readonly",
            "row_count": len(items),
            "limit": limit,
            "rows": items,
            "truncated": len(items) >= limit,
        }


class RedisInspectTool(ObservabilityTool):
    spec = ToolSpec(
        name="redis_inspect",
        description="Run a bounded read-only Redis inspection command such as PING, INFO, DBSIZE or TIME.",
        input_schema={
            "type": "object",
            "properties": {
                "command": {"type": "string", "enum": list(DEFAULT_REDIS_COMMANDS)},
                "section": {"type": "string"},
            },
        },
        kind="observability",
        metadata=_tool_metadata(capability="redis_inspect", side_effect="network"),
    )

    def _build_command(self, arguments: dict[str, Any]) -> list[str]:
        command = str(arguments.get("command") or "PING").strip().upper()
        allowed = {item.strip().upper() for item in self.policy.redis_allowed_commands}
        if command not in allowed:
            raise PermissionError("redis command is outside the observability allowlist")
        parts = [command]
        section = str(arguments.get("section") or "").strip()
        if section:
            if command != "INFO":
                raise ValueError("section is only supported for INFO")
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", section):
                raise ValueError("section contains unsupported characters")
            parts.append(section)
        return parts

    def _encode_resp(self, parts: Sequence[str]) -> bytes:
        payload = f"*{len(parts)}\r\n"
        for part in parts:
            encoded = part.encode("utf-8")
            payload += f"${len(encoded)}\r\n{part}\r\n"
        return payload.encode("utf-8")

    async def _read_resp(self, reader: asyncio.StreamReader) -> Any:
        line = await reader.readline()
        if not line:
            raise RuntimeError("redis connection closed before response")
        prefix = line[:1]
        value = line[1:].decode("utf-8", errors="replace").rstrip("\r\n")
        if prefix == b"+":
            return value
        if prefix == b"-":
            raise RuntimeError(value)
        if prefix == b":":
            return int(value)
        if prefix == b"$":
            length = int(value)
            if length < 0:
                return None
            data = await reader.readexactly(length)
            await reader.readexactly(2)
            return data.decode("utf-8", errors="replace")
        if prefix == b"*":
            return [await self._read_resp(reader) for _ in range(int(value))]
        return value

    def _parse_info(self, text: str) -> dict[str, Any]:
        sections: dict[str, dict[str, str]] = {}
        current = "default"
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("#"):
                current = line.lstrip("#").strip().lower().replace(" ", "_") or "default"
                sections.setdefault(current, {})
                continue
            if ":" in line:
                key, value = line.split(":", 1)
                sections.setdefault(current, {})[key] = value
        return sections

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        del context
        if not self.policy.redis_configured:
            raise RuntimeError("redis observability is not configured")
        command = self._build_command(arguments)
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(self.policy.redis_host, self.policy.redis_port),
            timeout=self.policy.timeout_seconds,
        )
        try:
            if self.policy.redis_password:
                writer.write(self._encode_resp(["AUTH", self.policy.redis_password]))
                await writer.drain()
                await self._read_resp(reader)
            writer.write(self._encode_resp(command))
            await writer.drain()
            response = await asyncio.wait_for(self._read_resp(reader), timeout=self.policy.timeout_seconds)
        finally:
            writer.close()
            await writer.wait_closed()

        result: dict[str, Any] = {
            "status": "completed",
            "host": self.policy.redis_host,
            "port": self.policy.redis_port,
            "command": command[0],
        }
        if command[0] == "INFO" and isinstance(response, str):
            result["sections"] = self._parse_info(response)
        else:
            result["response"] = _safe_json_value(response)
        return result


class HTTPHealthCheckTool(ObservabilityTool):
    spec = ToolSpec(
        name="http_health_check",
        description="Check an allowed service health URL and return status, latency and a bounded body preview.",
        input_schema={
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "expected_status": {"type": "integer", "minimum": 100, "maximum": 599},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 30},
            },
        },
        kind="observability",
        metadata=_tool_metadata(capability="http_health_check", side_effect="network"),
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        del context
        url = self._validate_http_url(arguments.get("url") or self.policy.default_health_url)
        expected_status = _clamp_int(arguments.get("expected_status"), default=200, minimum=100, maximum=599)
        timeout_seconds = _clamp_int(arguments.get("timeout_seconds"), default=self.policy.timeout_seconds, minimum=1, maximum=30)
        started = asyncio.get_running_loop().time()
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout_seconds)) as session:
            async with session.get(url) as response:
                body = await response.text(errors="replace")
                preview, truncated = self._truncate(_redact_text(body))
                elapsed_ms = int((asyncio.get_running_loop().time() - started) * 1000)
                return {
                    "status": "healthy" if response.status == expected_status else "unhealthy",
                    "url": url,
                    "status_code": response.status,
                    "expected_status": expected_status,
                    "latency_ms": elapsed_ms,
                    "content_type": response.headers.get("content-type", ""),
                    "body_preview": preview,
                    "truncated": truncated,
                }


class ServiceLogsTool(ObservabilityTool):
    spec = ToolSpec(
        name="service_logs",
        description="Read a bounded tail from an allowed service log file with secret redaction.",
        input_schema={
            "type": "object",
            "required": ["path"],
            "properties": {
                "path": {"type": "string"},
                "max_lines": {"type": "integer", "minimum": 1, "maximum": 1000},
                "query": {"type": "string"},
            },
        },
        kind="observability",
        metadata=_tool_metadata(capability="service_logs", risk_level="medium"),
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        del context
        path = self._resolve_log_path(arguments.get("path"))
        max_lines = _clamp_int(arguments.get("max_lines"), default=200, minimum=1, maximum=1000)
        query = str(arguments.get("query") or "").strip().lower()
        max_bytes = max(4096, min(2_000_000, self.policy.max_output_chars * 4))
        with path.open("rb") as handle:
            try:
                handle.seek(0, os.SEEK_END)
                size = handle.tell()
                handle.seek(max(0, size - max_bytes))
            except OSError:
                size = 0
            text = handle.read(max_bytes).decode("utf-8", errors="replace")
        lines = text.splitlines()
        if query:
            lines = [line for line in lines if query in line.lower()]
        selected = lines[-max_lines:]
        redacted_lines = [_redact_text(line) for line in selected]
        joined = "\n".join(redacted_lines)
        preview, output_truncated = self._truncate(joined)
        return {
            "status": "completed",
            "path": str(path),
            "line_count": len(redacted_lines),
            "max_lines": max_lines,
            "query": query or None,
            "content": preview,
            "truncated": output_truncated or len(lines) > len(selected),
        }


class MetricsQueryTool(ObservabilityTool):
    spec = ToolSpec(
        name="metrics_query",
        description="Fetch allowed Prometheus text metrics and return matching metric samples.",
        input_schema={
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "metric": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 500},
            },
        },
        kind="observability",
        metadata=_tool_metadata(capability="metrics_query", side_effect="network"),
    )

    def _validate_metric_filter(self, metric: str | None) -> str | None:
        if metric is None:
            if self.policy.allowed_metric_names:
                return None
            return None
        if not PROMETHEUS_METRIC_NAME_RE.fullmatch(metric):
            raise ValueError("metric must be a valid Prometheus metric name")
        if self.policy.allowed_metric_names and not _metric_name_allowed(metric, self.policy.allowed_metric_names):
            raise PermissionError("metric is outside the observability metrics allowlist")
        return metric

    def _parse_metrics(self, text: str, metric: str | None, limit: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        samples: list[dict[str, Any]] = []
        metric_filter = self._validate_metric_filter((metric or "").strip() or None)
        scanned_lines = 0
        skipped_by_allowlist = 0
        for raw_line in text.splitlines():
            scanned_lines += 1
            if scanned_lines > self.policy.max_metric_lines:
                break
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            name = line.split("{", 1)[0].split(" ", 1)[0]
            if metric_filter and metric_filter != name:
                continue
            if not _metric_name_allowed(name, self.policy.allowed_metric_names):
                skipped_by_allowlist += 1
                continue
            samples.append({"name": name, "line": line})
            if len(samples) >= limit:
                break
        return samples, {
            "line_budget": self.policy.max_metric_lines,
            "sample_budget": limit,
            "scanned_lines": min(scanned_lines, self.policy.max_metric_lines),
            "skipped_by_allowlist": skipped_by_allowlist,
            "line_budget_exhausted": scanned_lines > self.policy.max_metric_lines,
            "allowed_metric_names": list(self.policy.allowed_metric_names),
        }

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        del context
        url = self._validate_http_url(arguments.get("url") or self.policy.metrics_url)
        metric = self._validate_metric_filter(str(arguments.get("metric") or "").strip() or None)
        limit = _clamp_int(arguments.get("limit"), default=50, minimum=1, maximum=self.policy.max_metric_samples)
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.policy.timeout_seconds)) as session:
            async with session.get(url) as response:
                text = await response.text(errors="replace")
                samples, budget = self._parse_metrics(text, metric, limit)
                return {
                    "status": "completed" if response.status < 400 else "failed",
                    "url": url,
                    "status_code": response.status,
                    "metric": metric,
                    "sample_count": len(samples),
                    "samples": samples,
                    "budget": budget,
                    "truncated": len(samples) >= limit or bool(budget.get("line_budget_exhausted")),
                }


OBSERVABILITY_TOOL_TYPES = {
    "db_query_readonly": DBQueryReadonlyTool,
    "redis_inspect": RedisInspectTool,
    "http_health_check": HTTPHealthCheckTool,
    "service_logs": ServiceLogsTool,
    "metrics_query": MetricsQueryTool,
}


class ObservabilityToolProvider:
    def __init__(
        self,
        *,
        enabled_tool_names: Sequence[str],
        db_pool: Any | None = None,
        db_configured: bool = True,
        redis_configured: bool = False,
        redis_host: str = "127.0.0.1",
        redis_port: int = 6379,
        redis_password: str | None = None,
        redis_allowed_commands: Sequence[str] = DEFAULT_REDIS_COMMANDS,
        allowed_http_domains: Sequence[str] = (),
        allow_loopback_http: bool = True,
        default_health_url: str | None = None,
        metrics_url: str | None = None,
        allowed_metric_names: Sequence[str] = DEFAULT_METRIC_ALLOWED_NAMES,
        max_metric_lines: int = 5000,
        max_metric_samples: int = 500,
        log_roots: Sequence[str | Path] = (),
        log_extensions: Sequence[str] = DEFAULT_LOG_EXTENSIONS,
        max_rows: int = 100,
        max_output_chars: int = 40_000,
        timeout_seconds: int = 10,
    ) -> None:
        self.db_pool = db_pool
        resolved_log_roots = []
        for root in log_roots:
            root_text = str(root or "").strip()
            if not root_text:
                continue
            path = Path(root_text).expanduser()
            if path.exists():
                resolved_log_roots.append(path.resolve(strict=True))
        self.policy = ObservabilityPolicy(
            enabled_tool_names=tuple(name for name in enabled_tool_names if name in OBSERVABILITY_TOOL_TYPES),
            db_configured=db_configured,
            redis_configured=redis_configured,
            redis_host=redis_host,
            redis_port=redis_port,
            redis_password=redis_password,
            redis_allowed_commands=tuple(redis_allowed_commands),
            allowed_http_domains=tuple(allowed_http_domains),
            allow_loopback_http=allow_loopback_http,
            default_health_url=default_health_url,
            metrics_url=metrics_url,
            allowed_metric_names=tuple(name.strip() for name in allowed_metric_names if str(name or "").strip()),
            max_metric_lines=max_metric_lines,
            max_metric_samples=max_metric_samples,
            log_roots=tuple(dict.fromkeys(resolved_log_roots)),
            log_extensions=tuple(log_extensions),
            max_rows=max_rows,
            max_output_chars=max_output_chars,
            timeout_seconds=timeout_seconds,
        )
        self.enabled_tool_names = list(self.policy.enabled_tool_names)

    @classmethod
    def from_env(cls, *, db_pool: Any | None = None) -> "ObservabilityToolProvider":
        http_port = os.getenv("HTTP_PORT", "8000")
        health_path = os.getenv("HEALTH_CHECK_PATH", "/health")
        metrics_url = os.getenv("AGENT_OBSERVABILITY_METRICS_URL", "").strip() or None
        metrics_port = os.getenv("METRICS_PORT", "").strip()
        if metrics_url is None and metrics_port:
            metrics_url = f"http://127.0.0.1:{metrics_port}/metrics"
        return cls(
            enabled_tool_names=_parse_csv(os.getenv("AGENT_OBSERVABILITY_TOOLS"), DEFAULT_OBSERVABILITY_TOOL_NAMES),
            db_pool=db_pool,
            db_configured=_env_bool("AGENT_OBSERVABILITY_DB_CONFIGURED", True),
            redis_configured=_env_bool("AGENT_OBSERVABILITY_REDIS_CONFIGURED", False),
            redis_host=os.getenv("AGENT_OBSERVABILITY_REDIS_HOST", os.getenv("REDIS_HOST", "127.0.0.1")),
            redis_port=_clamp_int(
                os.getenv("AGENT_OBSERVABILITY_REDIS_PORT", os.getenv("REDIS_PORT", "6379")),
                default=6379,
                minimum=1,
                maximum=65535,
            ),
            redis_password=os.getenv("AGENT_OBSERVABILITY_REDIS_PASSWORD", os.getenv("REDIS_PASSWORD")) or None,
            redis_allowed_commands=_parse_csv(os.getenv("AGENT_OBSERVABILITY_REDIS_COMMANDS"), DEFAULT_REDIS_COMMANDS),
            allowed_http_domains=_parse_csv(os.getenv("AGENT_OBSERVABILITY_ALLOWED_DOMAINS"), ()),
            allow_loopback_http=_env_bool("AGENT_OBSERVABILITY_ALLOW_LOOPBACK_HTTP", True),
            default_health_url=os.getenv("AGENT_OBSERVABILITY_HEALTH_URL", f"http://127.0.0.1:{http_port}{health_path}"),
            metrics_url=metrics_url,
            allowed_metric_names=_parse_csv(
                os.getenv("AGENT_OBSERVABILITY_METRIC_ALLOWLIST"),
                DEFAULT_METRIC_ALLOWED_NAMES,
            ),
            max_metric_lines=_clamp_int(
                os.getenv("AGENT_OBSERVABILITY_METRIC_MAX_LINES"),
                default=5000,
                minimum=100,
                maximum=200_000,
            ),
            max_metric_samples=_clamp_int(
                os.getenv("AGENT_OBSERVABILITY_METRIC_MAX_SAMPLES"),
                default=500,
                minimum=1,
                maximum=5000,
            ),
            log_roots=_parse_csv(os.getenv("AGENT_OBSERVABILITY_LOG_ROOTS"), ()),
            log_extensions=_parse_csv(os.getenv("AGENT_OBSERVABILITY_LOG_EXTENSIONS"), DEFAULT_LOG_EXTENSIONS),
            max_rows=_clamp_int(os.getenv("AGENT_OBSERVABILITY_MAX_ROWS"), default=100, minimum=1, maximum=500),
            max_output_chars=_clamp_int(
                os.getenv("AGENT_OBSERVABILITY_MAX_OUTPUT_CHARS"),
                default=40_000,
                minimum=1_000,
                maximum=200_000,
            ),
            timeout_seconds=_clamp_int(os.getenv("AGENT_OBSERVABILITY_TIMEOUT_SECONDS"), default=10, minimum=1, maximum=30),
        )

    def _tool_available(self, name: str) -> bool:
        if name == "db_query_readonly":
            return self.policy.db_configured
        if name == "redis_inspect":
            return self.policy.redis_configured
        if name == "service_logs":
            return bool(self.policy.log_roots)
        if name == "metrics_query":
            return _host_allowed_for_policy(self.policy.metrics_url, self.policy)
        if name == "http_health_check":
            return _host_allowed_for_policy(self.policy.default_health_url, self.policy)
        return False

    def _build_tool(self, name: str) -> BaseTool | None:
        tool_type = OBSERVABILITY_TOOL_TYPES.get(name)
        if tool_type is None or name not in self.enabled_tool_names:
            return None
        if not self._tool_available(name):
            return None
        return tool_type(self.policy, self.db_pool)

    async def get(self, name: str, context: ToolLookupContext | None = None) -> BaseTool | None:
        del context
        return self._build_tool(name)

    async def get_spec(self, name: str, context: ToolLookupContext | None = None) -> dict | None:
        del context
        tool = self._build_tool(name)
        if tool is None:
            return None
        return {
            "name": tool.spec.name,
            "description": tool.spec.description,
            "input_schema": tool.spec.input_schema,
            "kind": tool.spec.kind,
            "metadata": tool.spec.metadata,
        }

    async def list_specs(self, context: ToolLookupContext | None = None) -> list[dict]:
        del context
        items = []
        for name in self.enabled_tool_names:
            spec = await self.get_spec(name)
            if spec is not None:
                items.append(spec)
        return items

    def status_summary(self, *, enabled: bool = True) -> dict[str, Any]:
        return {
            "enabled": enabled,
            "configured": True,
            "enabled_tools": list(self.enabled_tool_names),
            "available_tools": [name for name in self.enabled_tool_names if enabled and self._tool_available(name)],
            "db_configured": self.policy.db_configured,
            "redis_configured": self.policy.redis_configured,
            "redis_host": self.policy.redis_host if self.policy.redis_configured else None,
            "redis_port": self.policy.redis_port if self.policy.redis_configured else None,
            "allowed_http_domains": list(self.policy.allowed_http_domains),
            "allow_loopback_http": self.policy.allow_loopback_http,
            "default_health_url": self.policy.default_health_url,
            "metrics_url_configured": bool(self.policy.metrics_url),
            "allowed_metric_names": list(self.policy.allowed_metric_names),
            "max_metric_lines": self.policy.max_metric_lines,
            "max_metric_samples": self.policy.max_metric_samples,
            "log_roots": [str(path) for path in self.policy.log_roots],
            "max_rows": self.policy.max_rows,
            "max_output_chars": self.policy.max_output_chars,
            "timeout_seconds": self.policy.timeout_seconds,
            "audit_report": build_observability_audit_report(self.policy, enabled=enabled),
        }
