from __future__ import annotations

import base64
import hashlib
import os
import posixpath
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import unescape
from io import BytesIO
from typing import Any, Literal, Sequence
from urllib.parse import unquote, urlencode, urlparse

import aiohttp
from bs4 import BeautifulSoup

from ai_runtime.core.agent_runtime.tools.base import BaseTool, ToolContext, ToolLookupContext, ToolSpec
from ai_runtime.core.agent_runtime.tools.failure_taxonomy import build_failure_recovery, build_failure_taxonomy
from ai_runtime.core.agent_runtime.web_quality import evaluate_search_result_items


DEFAULT_WEB_TOOL_NAMES = (
    "fetch_url",
    "open_page",
    "extract_page_text",
    "web_search",
    "download_file",
)
DEFAULT_BROWSER_TOOL_NAMES = (
    "browser_open",
    "browser_click",
    "browser_type",
    "browser_screenshot",
    "browser_snapshot",
    "browser_close",
    "browser_verify",
    "pdf_extract",
)
DEFAULT_ALLOWED_CONTENT_TYPES = (
    "text/html",
    "text/plain",
    "application/json",
    "application/xml",
    "text/xml",
)
DEFAULT_DOWNLOAD_CONTENT_TYPES = DEFAULT_ALLOWED_CONTENT_TYPES + (
    "application/pdf",
    "application/zip",
    "application/gzip",
    "application/x-gzip",
    "application/octet-stream",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
DEFAULT_SEARCH_ALLOWED_SCHEMES = ("https",)


def _parse_csv(value: str | None, default: Sequence[str]) -> list[str]:
    if value is None or not value.strip():
        return [item for item in default]
    return [item.strip() for item in value.split(",") if item.strip()]


def _clamp_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _tool_metadata(
    *,
    available: bool,
    capability: str = "web",
    risk_level: str = "medium",
    unavailable_reason: str = "web network access is not configured",
    recovery_actions: Sequence[str] | None = None,
) -> dict[str, Any]:
    metadata = {
        "provider": "web",
        "capability": capability,
        "access_level": "network",
        "side_effect": "network",
        "requires_workspace": False,
        "requires_sandbox": False,
        "risk_level": risk_level,
        "failure_taxonomy": build_failure_taxonomy("web"),
    }
    if not available:
        metadata.update(
            {
                "status": "unavailable",
                "unavailable_reason": unavailable_reason,
                "recovery_actions": list(recovery_actions or [
                    "Set AGENT_WEB_ENABLED=true and AGENT_WEB_NETWORK_CONFIGURED=true after reviewing domain policy.",
                    "Configure AGENT_WEB_ALLOWED_DOMAINS or AGENT_WEB_DENIED_DOMAINS before exposing web tools.",
                ]),
            }
        )
    return metadata


@dataclass(frozen=True)
class WebPolicy:
    network_configured: bool = False
    allowed_domains: tuple[str, ...] = ()
    denied_domains: tuple[str, ...] = ()
    allowed_content_types: tuple[str, ...] = DEFAULT_ALLOWED_CONTENT_TYPES
    allowed_download_content_types: tuple[str, ...] = DEFAULT_DOWNLOAD_CONTENT_TYPES
    max_response_bytes: int = 1_000_000
    max_download_bytes: int = 2_000_000
    max_output_chars: int = 40_000
    timeout_seconds: int = 20
    user_agent: str = "AI-Platform-Agent/1.0"
    search_endpoint: str | None = None
    search_require_url: bool = True
    search_require_title: bool = True
    search_require_snippet: bool = False
    search_allowed_schemes: tuple[str, ...] = DEFAULT_SEARCH_ALLOWED_SCHEMES
    search_reject_disallowed_domains: bool = True
    search_reject_duplicates: bool = True
    browser_configured: bool = False
    browser_backend: str = "playwright"
    browser_name: str = "chromium"
    browser_headless: bool = True
    browser_max_sessions: int = 4
    browser_session_ttl_seconds: int = 900
    browser_snapshot_chars: int = 60_000
    pdf_max_pages: int = 20


@dataclass
class BrowserSession:
    session_id: str
    url: str
    title: str
    playwright: Any
    browser: Any
    context: Any
    page: Any
    created_at: float
    updated_at: float
    viewport: dict[str, int]
    console_messages: list[dict[str, Any]] = field(default_factory=list)
    network_errors: list[dict[str, Any]] = field(default_factory=list)


SearchQualityDisposition = Literal["accepted", "rejected", "warning"]


def _browser_runtime_status() -> tuple[bool, str]:
    try:
        import playwright.async_api  # noqa: F401
    except ImportError:
        return False, "playwright is not installed"
    return True, "browser runtime is available"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _start_playwright() -> Any:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError("playwright is not installed") from exc
    return await async_playwright().start()


async def _safe_page_title(page: Any) -> str:
    try:
        return str(await page.title() or "").strip()
    except Exception:
        return ""


def _short_text(value: Any, limit: int = 400) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _request_failure_text(request: Any) -> str:
    try:
        failure = getattr(request, "failure", None)
        if callable(failure):
            failure = failure()
    except Exception:
        failure = None
    if isinstance(failure, dict):
        return str(failure.get("errorText") or failure.get("error_text") or "").strip()
    return str(failure or "").strip()


class WebTool(BaseTool):
    def __init__(self, policy: WebPolicy) -> None:
        self.policy = policy

    def spec_dict(self) -> dict[str, Any]:
        return {
            "name": self.spec.name,
            "description": self.spec.description,
            "input_schema": self.spec.input_schema,
            "kind": self.spec.kind,
            "metadata": _tool_metadata(
                available=self.policy.network_configured,
                capability=str(self.spec.metadata.get("capability") or "web"),
                risk_level=str(self.spec.metadata.get("risk_level") or "medium"),
            ),
        }

    def _truncate_text(self, text: str, max_chars: int | None = None) -> tuple[str, bool]:
        limit = max_chars or self.policy.max_output_chars
        if len(text) <= limit:
            return text, False
        return text[:limit], True

    def _validate_url(self, raw_url: Any) -> str:
        url = str(raw_url or "").strip()
        if not url:
            raise ValueError("url is required")
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise PermissionError("only http and https URLs are allowed")
        host = (parsed.hostname or "").lower()
        if not host:
            raise ValueError("url host is required")
        if self.policy.denied_domains and self._domain_matches(host, self.policy.denied_domains):
            raise PermissionError("url host is denied by web policy")
        if self.policy.allowed_domains and not self._domain_matches(host, self.policy.allowed_domains):
            raise PermissionError("url host is outside allowed web domains")
        return url

    def _validate_search_item_url(self, raw_url: Any) -> str:
        url = str(raw_url or "").strip()
        if not url:
            return ""
        parsed = urlparse(url)
        if self.policy.search_allowed_schemes and parsed.scheme.lower() not in set(self.policy.search_allowed_schemes):
            raise PermissionError("search result URL uses a disallowed scheme")
        return self._validate_url(url)

    @staticmethod
    def _domain_matches(host: str, patterns: Sequence[str]) -> bool:
        for pattern in patterns:
            normalized = pattern.strip().lower()
            if not normalized:
                continue
            if normalized.startswith("*."):
                suffix = normalized[1:]
                if host.endswith(suffix):
                    return True
                continue
            if host == normalized or host.endswith(f".{normalized}"):
                return True
        return False

    def _content_type_allowed(self, content_type: str) -> bool:
        return self._content_type_matches(content_type, self.policy.allowed_content_types)

    @staticmethod
    def _content_type_matches(content_type: str, allowed_types: Sequence[str]) -> bool:
        media_type = content_type.split(";", 1)[0].strip().lower()
        return any(media_type == allowed.lower() for allowed in allowed_types)

    def _download_content_type_allowed(self, content_type: str) -> bool:
        return self._content_type_matches(content_type, self.policy.allowed_download_content_types)

    def _failure_recovery(self, category: str, *, message: str | None = None) -> dict[str, Any]:
        return build_failure_recovery("web", category, message=message)

    def _search_quality_checks(self, items: Sequence[Any], *, limit: int) -> dict[str, Any]:
        return evaluate_search_result_items(items, self.policy, limit=limit)

    @staticmethod
    def _filename_from_headers(url: str, headers: Any) -> str:
        content_disposition = str(headers.get("content-disposition") or "")
        for part in content_disposition.split(";"):
            key, separator, value = part.strip().partition("=")
            if not separator:
                continue
            if key.lower() == "filename*":
                encoded = value.strip().strip('"')
                if "''" in encoded:
                    encoded = encoded.split("''", 1)[1]
                candidate = unquote(encoded).strip()
            elif key.lower() == "filename":
                candidate = unquote(value.strip().strip('"')).strip()
            else:
                continue
            if candidate:
                return posixpath.basename(candidate.replace("\\", "/"))
        parsed_path = urlparse(url).path
        filename = posixpath.basename(unquote(parsed_path).rstrip("/"))
        return filename or "download"

    async def _fetch(self, url: str, *, max_bytes: Any = None) -> dict[str, Any]:
        if not self.policy.network_configured:
            raise RuntimeError("web network access is not configured")
        validated_url = self._validate_url(url)
        byte_limit = _clamp_int(
            max_bytes,
            default=self.policy.max_response_bytes,
            minimum=1_000,
            maximum=self.policy.max_response_bytes,
        )
        timeout = aiohttp.ClientTimeout(total=self.policy.timeout_seconds)
        headers = {"User-Agent": self.policy.user_agent}
        fetched_at = datetime.now(timezone.utc).isoformat()
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.get(validated_url, allow_redirects=True) as response:
                    content_type = response.headers.get("content-type", "")
                    if not self._content_type_allowed(content_type):
                        message = f"content type is not allowed: {content_type or 'unknown'}"
                        return {
                            "url": str(response.url),
                            "requested_url": validated_url,
                            "status": response.status,
                            "headers": {
                                "content_type": content_type,
                                "content_length": response.headers.get("content-length"),
                            },
                            "text": "",
                            "truncated": False,
                            "fetched_at": fetched_at,
                            "failure_category": "content_type_denied",
                            "error": message,
                            "recovery": self._failure_recovery("content_type_denied", message=message),
                        }
                    data = await response.content.read(byte_limit + 1)
                    truncated = len(data) > byte_limit
                    if truncated:
                        data = data[:byte_limit]
                    text = data.decode(response.charset or "utf-8", errors="replace")
                    return {
                        "url": str(response.url),
                        "requested_url": validated_url,
                        "status": response.status,
                        "headers": {
                            "content_type": content_type,
                            "content_length": response.headers.get("content-length"),
                        },
                        "text": text,
                        "truncated": truncated,
                        "fetched_at": fetched_at,
                    }
        except TimeoutError:
            return {
                "url": validated_url,
                "requested_url": validated_url,
                "status": None,
                "headers": {},
                "text": "",
                "truncated": False,
                "fetched_at": fetched_at,
                "failure_category": "timeout",
                "error": "request timed out",
                "recovery": self._failure_recovery("timeout"),
            }
        except aiohttp.ClientError as exc:
            message = str(exc)
            return {
                "url": validated_url,
                "requested_url": validated_url,
                "status": None,
                "headers": {},
                "text": "",
                "truncated": False,
                "fetched_at": fetched_at,
                "failure_category": "network_error",
                "error": message,
                "recovery": self._failure_recovery("network_error", message=message),
            }

    async def _download(self, url: str, *, max_bytes: Any = None) -> dict[str, Any]:
        if not self.policy.network_configured:
            raise RuntimeError("web network access is not configured")
        validated_url = self._validate_url(url)
        byte_limit = _clamp_int(
            max_bytes,
            default=self.policy.max_download_bytes,
            minimum=1_000,
            maximum=self.policy.max_download_bytes,
        )
        timeout = aiohttp.ClientTimeout(total=self.policy.timeout_seconds)
        headers = {"User-Agent": self.policy.user_agent}
        fetched_at = datetime.now(timezone.utc).isoformat()
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.get(validated_url, allow_redirects=True) as response:
                    content_type = response.headers.get("content-type", "")
                    if not self._download_content_type_allowed(content_type):
                        message = f"content type is not allowed for download: {content_type or 'unknown'}"
                        return {
                            "url": str(response.url),
                            "requested_url": validated_url,
                            "status": response.status,
                            "headers": {
                                "content_type": content_type,
                                "content_length": response.headers.get("content-length"),
                                "content_disposition": response.headers.get("content-disposition"),
                            },
                            "filename": self._filename_from_headers(str(response.url), response.headers),
                            "bytes": 0,
                            "sha256": "",
                            "data": b"",
                            "truncated": False,
                            "fetched_at": fetched_at,
                            "failure_category": "content_type_denied",
                            "error": message,
                            "recovery": self._failure_recovery("content_type_denied", message=message),
                        }
                    data = await response.content.read(byte_limit + 1)
                    truncated = len(data) > byte_limit
                    if truncated:
                        data = data[:byte_limit]
                    return {
                        "url": str(response.url),
                        "requested_url": validated_url,
                        "status": response.status,
                        "headers": {
                            "content_type": content_type,
                            "content_length": response.headers.get("content-length"),
                            "content_disposition": response.headers.get("content-disposition"),
                        },
                        "filename": self._filename_from_headers(str(response.url), response.headers),
                        "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "data": data,
                        "truncated": truncated,
                        "fetched_at": fetched_at,
                    }
        except TimeoutError:
            return {
                "url": validated_url,
                "requested_url": validated_url,
                "status": None,
                "headers": {},
                "filename": self._filename_from_headers(validated_url, {}),
                "bytes": 0,
                "sha256": "",
                "data": b"",
                "truncated": False,
                "fetched_at": fetched_at,
                "failure_category": "timeout",
                "error": "request timed out",
                "recovery": self._failure_recovery("timeout"),
            }
        except aiohttp.ClientError as exc:
            message = str(exc)
            return {
                "url": validated_url,
                "requested_url": validated_url,
                "status": None,
                "headers": {},
                "filename": self._filename_from_headers(validated_url, {}),
                "bytes": 0,
                "sha256": "",
                "data": b"",
                "truncated": False,
                "fetched_at": fetched_at,
                "failure_category": "network_error",
                "error": message,
                "recovery": self._failure_recovery("network_error", message=message),
            }

    def _extract_page(self, fetched: dict[str, Any], *, max_chars: Any = None) -> dict[str, Any]:
        html = str(fetched.get("text") or "")
        soup = BeautifulSoup(html, "html.parser")
        for node in soup(["script", "style", "noscript"]):
            node.decompose()
        title = unescape(soup.title.get_text(" ", strip=True)) if soup.title else ""
        text = soup.get_text("\n", strip=True)
        text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        text, text_truncated = self._truncate_text(
            text,
            _clamp_int(max_chars, default=self.policy.max_output_chars, minimum=100, maximum=self.policy.max_output_chars),
        )
        return {
            "url": fetched.get("url"),
            "requested_url": fetched.get("requested_url"),
            "status": fetched.get("status"),
            "title": title,
            "text": text,
            "truncated": bool(fetched.get("truncated")) or text_truncated,
            "fetched_at": fetched.get("fetched_at"),
            "source": "web",
        }


class FetchURLTool(WebTool):
    spec = ToolSpec(
        name="fetch_url",
        description="Fetch a policy-allowed URL and return bounded text content with source metadata.",
        input_schema={
            "type": "object",
            "required": ["url"],
            "properties": {
                "url": {"type": "string"},
                "max_bytes": {"type": "integer", "minimum": 1000, "maximum": 2000000},
            },
        },
        kind="web",
        metadata=_tool_metadata(available=False, capability="web_research"),
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        return await self._fetch(str(arguments.get("url") or ""), max_bytes=arguments.get("max_bytes"))


class OpenPageTool(WebTool):
    spec = ToolSpec(
        name="open_page",
        description="Open a policy-allowed web page and extract title plus readable text.",
        input_schema={
            "type": "object",
            "required": ["url"],
            "properties": {
                "url": {"type": "string"},
                "max_chars": {"type": "integer", "minimum": 100, "maximum": 100000},
            },
        },
        kind="web",
        metadata=_tool_metadata(available=False, capability="web_research"),
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        fetched = await self._fetch(str(arguments.get("url") or ""))
        if fetched.get("error"):
            return fetched
        return self._extract_page(fetched, max_chars=arguments.get("max_chars"))


class ExtractPageTextTool(OpenPageTool):
    spec = ToolSpec(
        name="extract_page_text",
        description="Fetch a policy-allowed page and return normalized readable text for citation and summarization.",
        input_schema=OpenPageTool.spec.input_schema,
        kind="web",
        metadata=_tool_metadata(available=False, capability="web_research"),
    )


class WebSearchTool(WebTool):
    spec = ToolSpec(
        name="web_search",
        description="Run a policy-controlled web search through a configured JSON search endpoint.",
        input_schema={
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 10},
            },
        },
        kind="web",
        metadata=_tool_metadata(available=False, capability="web_research"),
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        if not self.policy.search_endpoint:
            raise RuntimeError("web search endpoint is not configured")
        query = str(arguments.get("query") or "").strip()
        if not query:
            raise ValueError("query is required")
        limit = _clamp_int(arguments.get("limit"), default=5, minimum=1, maximum=10)
        separator = "&" if "?" in self.policy.search_endpoint else "?"
        url = f"{self.policy.search_endpoint}{separator}{urlencode({'q': query, 'limit': limit})}"
        fetched = await self._fetch(url)
        if fetched.get("error"):
            return {**fetched, "query": query, "items": [], "accepted": [], "rejected": [], "quality": {"status": "warning", "summary": fetched.get("error") or "search failed"}}
        payload = fetched.get("text") or ""
        raw_items = self._parse_search_items(payload, limit)
        quality = self._search_quality_checks(raw_items, limit=limit)
        failure_recovery = None
        if quality["accepted_count"] <= 0:
            failure_recovery = self._failure_recovery("search_no_results")
        result = {
            "query": query,
            "items": quality["accepted"],
            "accepted": quality["accepted"],
            "rejected": quality["rejected"],
            "total": quality["accepted_count"],
            "accepted_count": quality["accepted_count"],
            "rejected_count": quality["rejected_count"],
            "quality": {
                "status": "accepted" if quality["accepted_count"] > 0 else "warning",
                "accepted_count": quality["accepted_count"],
                "rejected_count": quality["rejected_count"],
                "summary": "search results passed quality checks" if quality["accepted_count"] > 0 else "search returned no acceptable results",
                "rules": {
                    "require_url": self.policy.search_require_url,
                    "require_title": self.policy.search_require_title,
                    "require_snippet": self.policy.search_require_snippet,
                    "allowed_schemes": list(self.policy.search_allowed_schemes),
                    "reject_disallowed_domains": self.policy.search_reject_disallowed_domains,
                    "reject_duplicates": self.policy.search_reject_duplicates,
                },
            },
            "url": fetched.get("url"),
            "fetched_at": fetched.get("fetched_at"),
            "source": "web_search",
            "truncated": fetched.get("truncated"),
        }
        if failure_recovery:
            result["failure_category"] = "search_no_results"
            result["recovery"] = failure_recovery
        return result

    @staticmethod
    def _parse_search_items(payload: str, limit: int) -> list[dict[str, Any]]:
        import json

        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, dict):
            raw_items = parsed.get("items") or parsed.get("results") or parsed.get("data") or []
        else:
            raw_items = parsed
        if not isinstance(raw_items, list):
            return []
        items: list[dict[str, Any]] = []
        for item in raw_items[:limit]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("name") or item.get("url") or "").strip()
            url = str(item.get("url") or item.get("link") or item.get("href") or "").strip()
            snippet = str(item.get("snippet") or item.get("summary") or item.get("text") or "").strip()
            if not title and not url and not snippet:
                continue
            items.append({"title": title or url, "url": url, "snippet": snippet})
        return items


class DownloadFileTool(WebTool):
    spec = ToolSpec(
        name="download_file",
        description="Download a policy-allowed file and return bounded file artifact metadata plus inline content when within policy.",
        input_schema={
            "type": "object",
            "required": ["url"],
            "properties": {
                "url": {"type": "string"},
                "max_bytes": {"type": "integer", "minimum": 1000, "maximum": 5000000},
                "include_data": {"type": "boolean", "default": True},
            },
        },
        kind="web",
        metadata=_tool_metadata(available=False, capability="web_research", risk_level="high"),
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        downloaded = await self._download(str(arguments.get("url") or ""), max_bytes=arguments.get("max_bytes"))
        data = downloaded.pop("data", b"")
        include_data = bool(arguments.get("include_data", True))
        content_type = str(downloaded.get("headers", {}).get("content_type") or "").split(";", 1)[0].strip()
        file_entry: dict[str, Any] = {
            "name": downloaded.get("filename") or "download",
            "path": downloaded.get("filename") or "download",
            "mime_type": content_type or "application/octet-stream",
            "size_bytes": downloaded.get("bytes") or 0,
            "source_url": downloaded.get("url") or downloaded.get("requested_url") or "",
            "description": "Downloaded web file",
            "metadata": {
                "requested_url": downloaded.get("requested_url"),
                "status": downloaded.get("status"),
                "fetched_at": downloaded.get("fetched_at"),
                "sha256": downloaded.get("sha256"),
                "truncated": downloaded.get("truncated"),
                "content_length": downloaded.get("headers", {}).get("content_length"),
                "failure_category": downloaded.get("failure_category"),
            },
        }
        if include_data and data and not downloaded.get("truncated"):
            file_entry["data"] = base64.b64encode(data).decode("ascii")
        else:
            file_entry["url"] = downloaded.get("url")
        if downloaded.get("error"):
            file_entry["preview_text"] = str(downloaded.get("error") or "")

        return {
            "url": downloaded.get("url"),
            "requested_url": downloaded.get("requested_url"),
            "status": downloaded.get("status"),
            "filename": downloaded.get("filename"),
            "content_type": content_type,
            "bytes": downloaded.get("bytes") or 0,
            "sha256": downloaded.get("sha256"),
            "truncated": downloaded.get("truncated"),
            "fetched_at": downloaded.get("fetched_at"),
            "failure_category": downloaded.get("failure_category"),
            "recovery": downloaded.get("recovery"),
            "error": downloaded.get("error"),
            "files": [file_entry],
            "source": "web_download",
        }


class BrowserTool(WebTool):
    def __init__(self, policy: WebPolicy, sessions: dict[str, BrowserSession]) -> None:
        super().__init__(policy)
        self.sessions = sessions

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("BrowserTool is a shared base class")

    def spec_dict(self) -> dict[str, Any]:
        runtime_available, runtime_reason = _browser_runtime_status()
        available = self.policy.network_configured and self.policy.browser_configured and runtime_available
        if not self.policy.network_configured:
            reason = "web network access is not configured"
        elif not self.policy.browser_configured:
            reason = "browser runtime is not configured"
        else:
            reason = runtime_reason
        metadata = _tool_metadata(
            available=available,
            capability="browser_verify",
            risk_level=str(self.spec.metadata.get("risk_level") or "high"),
            unavailable_reason=reason,
            recovery_actions=[
                "Set AGENT_BROWSER_ENABLED=true and AGENT_BROWSER_CONFIGURED=true after reviewing browser policy.",
                "Install and verify the configured browser runtime, for example: playwright install chromium.",
                "Keep AGENT_WEB_ALLOWED_DOMAINS constrained before exposing browser tools.",
            ],
        )
        metadata.update(
            {
                "requires_browser": True,
                "browser_backend": self.policy.browser_backend,
                "browser_name": self.policy.browser_name,
            }
        )
        return {
            "name": self.spec.name,
            "description": self.spec.description,
            "input_schema": self.spec.input_schema,
            "kind": self.spec.kind,
            "metadata": metadata,
        }

    def _validate_browser_available(self) -> None:
        if not self.policy.network_configured:
            raise RuntimeError("web network access is not configured")
        if not self.policy.browser_configured:
            raise RuntimeError("browser runtime is not configured")
        available, reason = _browser_runtime_status()
        if not available:
            raise RuntimeError(reason)

    def _browser_failure_result(self, category: str, *, message: str, status: str = "failed") -> dict[str, Any]:
        return {
            "status": status,
            "failure_category": category,
            "error": message,
            "recovery": self._failure_recovery(category, message=message),
            "source": self.spec.name,
        }

    def _get_session(self, session_id: Any) -> BrowserSession:
        text = str(session_id or "").strip()
        if not text:
            raise ValueError("session_id is required")
        session = self.sessions.get(text)
        if session is None:
            raise ValueError("browser session was not found")
        return session

    def _session_age_seconds(self, session: BrowserSession) -> int:
        return max(0, int(time.monotonic() - session.updated_at))

    def _session_is_stale(self, session: BrowserSession) -> bool:
        return self._session_age_seconds(session) >= self.policy.browser_session_ttl_seconds

    async def _reap_stale_sessions(self) -> dict[str, Any]:
        expired: list[str] = []
        for session_id, session in list(self.sessions.items()):
            if self._session_is_stale(session):
                expired.append(session_id)
        for session_id in expired:
            await self._close_session(session_id)
        return {
            "expired_session_ids": expired,
            "expired_count": len(expired),
        }

    def _coerce_viewport(self, arguments: dict[str, Any]) -> dict[str, int]:
        width = _clamp_int(arguments.get("width"), default=1280, minimum=320, maximum=3840)
        height = _clamp_int(arguments.get("height"), default=720, minimum=240, maximum=2160)
        return {"width": width, "height": height}

    def _record_console_message(self, session: BrowserSession, message_type: Any, text: Any) -> None:
        session.console_messages.append(
            {
                "type": "console",
                "level": _short_text(message_type, 32) or "log",
                "text": _short_text(text, 500),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        session.console_messages = session.console_messages[-50:]

    def _record_network_error(self, session: BrowserSession, request: Any) -> None:
        failure = None
        try:
            failure = request.failure
            if callable(failure):
                failure = failure()
        except Exception:
            failure = None
        failure_text = ""
        if isinstance(failure, dict):
            failure_text = str(failure.get("errorText") or failure.get("error_text") or "")
        elif failure is not None:
            failure_text = str(failure)
        session.network_errors.append(
            {
                "url": _short_text(getattr(request, "url", ""), 500),
                "method": _short_text(getattr(request, "method", ""), 16),
                "text": _short_text(failure_text or "request failed", 500),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        session.network_errors = session.network_errors[-50:]

    async def _collect_page_diagnostics(self, session: BrowserSession) -> None:
        page = session.page
        try:
            console_messages = await page.evaluate(
                """
                () => Array.isArray(window.__aiPlatformBrowserLogs)
                  ? window.__aiPlatformBrowserLogs.slice(-12)
                  : []
                """
            )
        except Exception:
            console_messages = []
        if isinstance(console_messages, list):
            for item in console_messages:
                if not isinstance(item, dict):
                    continue
                self._record_console_message(
                    session,
                    item.get("level") or item.get("type") or "log",
                    item.get("text") or "",
                )

        try:
            network_errors = await page.evaluate(
                """
                () => Array.isArray(window.__aiPlatformNetworkErrors)
                  ? window.__aiPlatformNetworkErrors.slice(-8)
                  : []
                """
            )
        except Exception:
            network_errors = []
        if isinstance(network_errors, list):
            for item in network_errors:
                if not isinstance(item, dict):
                    continue
                session.network_errors.append(
                    {
                        "url": _short_text(item.get("url"), 500),
                        "method": _short_text(item.get("method"), 16),
                        "text": _short_text(item.get("text"), 500),
                        "timestamp": item.get("timestamp") or datetime.now(timezone.utc).isoformat(),
                    }
                )
            session.network_errors = session.network_errors[-50:]

    async def _page_text(self, page: Any, max_chars: Any = None) -> str:
        try:
            text = await page.locator("body").inner_text(timeout=2_000)
        except Exception:
            try:
                text = await page.content()
            except Exception:
                text = ""
        return self._truncate_text(
            str(text or ""),
            _clamp_int(max_chars, default=self.policy.max_output_chars, minimum=100, maximum=self.policy.max_output_chars),
        )[0]

    async def _snapshot_payload(self, session: BrowserSession, *, max_chars: Any = None) -> dict[str, Any]:
        page = session.page
        await self._collect_page_diagnostics(session)
        html = ""
        try:
            html = await page.content()
        except Exception:
            html = ""
        text = await self._page_text(page, max_chars=max_chars)
        html, html_truncated = self._truncate_text(
            html,
            _clamp_int(max_chars, default=self.policy.browser_snapshot_chars, minimum=500, maximum=self.policy.browser_snapshot_chars),
        )
        title = await _safe_page_title(page)
        url = str(getattr(page, "url", "") or session.url)
        self._validate_url(url)
        session.url = url
        session.title = title
        session.updated_at = time.monotonic()
        return {
            "session_id": session.session_id,
            "url": url,
            "title": title,
            "text": text,
            "html": html,
            "truncated": html_truncated or len(text) >= self.policy.max_output_chars,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "viewport": session.viewport,
            "console_messages": session.console_messages[-12:],
            "network_errors": session.network_errors[-8:],
            "source": "browser_snapshot",
        }

    async def _close_session(self, session_id: str) -> bool:
        session = self.sessions.pop(session_id, None)
        if session is None:
            return False
        for closeable in (session.context, session.browser):
            if closeable is None:
                continue
            try:
                await closeable.close()
            except Exception:
                pass
        if session.playwright is not None:
            try:
                await session.playwright.stop()
            except Exception:
                pass
        return True

    def browser_session_snapshot(self) -> dict[str, Any]:
        session_items = []
        expired_session_ids: list[str] = []
        now = time.monotonic()
        for session in self.sessions.values():
            age_seconds = max(0, int(now - session.updated_at))
            if age_seconds >= self.policy.browser_session_ttl_seconds:
                expired_session_ids.append(session.session_id)
            session_items.append(
                {
                    "session_id": session.session_id,
                    "url": session.url,
                    "title": session.title,
                    "created_at": session.created_at,
                    "updated_at": session.updated_at,
                    "age_seconds": age_seconds,
                    "viewport": session.viewport,
                    "console_message_count": len(session.console_messages),
                    "network_error_count": len(session.network_errors),
                }
            )
        oldest_age = max((item["age_seconds"] for item in session_items), default=None)
        active_session_count = max(0, len(session_items) - len(expired_session_ids))
        return {
            "session_count": len(session_items),
            "active_session_count": active_session_count,
            "expired_session_count": len(expired_session_ids),
            "expired_session_ids": expired_session_ids,
            "oldest_session_age_seconds": oldest_age,
            "session_ttl_seconds": self.policy.browser_session_ttl_seconds,
            "sessions": session_items,
            "recovery_actions": (
                ["Use browser_close to release stale sessions.", "Tune AGENT_BROWSER_SESSION_TTL_SECONDS for long-running verification flows."]
                if session_items
                else []
            ),
        }

    async def browser_session_summary(self) -> dict[str, Any]:
        reap = await self._reap_stale_sessions()
        snapshot = self.browser_session_snapshot()
        snapshot["expired_session_count"] = reap["expired_count"]
        snapshot["expired_session_ids"] = reap["expired_session_ids"]
        return snapshot


class BrowserOpenTool(BrowserTool):
    spec = ToolSpec(
        name="browser_open",
        description="Open a policy-allowed page in the configured sandbox browser and return a managed browser session plus a text snapshot.",
        input_schema={
            "type": "object",
            "required": ["url"],
            "properties": {
                "url": {"type": "string"},
                "width": {"type": "integer", "minimum": 320, "maximum": 3840},
                "height": {"type": "integer", "minimum": 240, "maximum": 2160},
                "wait_until": {"type": "string", "enum": ["load", "domcontentloaded", "networkidle"]},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 120},
                "max_chars": {"type": "integer", "minimum": 100, "maximum": 100000},
            },
        },
        kind="web",
        metadata=_tool_metadata(available=False, capability="browser_verify", risk_level="high"),
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            self._validate_browser_available()
        except RuntimeError as exc:
            return self._browser_failure_result("browser_unavailable", message=str(exc))
        await self._reap_stale_sessions()
        if len(self.sessions) >= self.policy.browser_max_sessions:
            return self._browser_failure_result("browser_session_limit", message="browser session limit has been reached")
        url = self._validate_url(arguments.get("url"))
        viewport = self._coerce_viewport(arguments)
        timeout_ms = _clamp_int(arguments.get("timeout_seconds"), default=self.policy.timeout_seconds, minimum=1, maximum=120) * 1000
        wait_until = str(arguments.get("wait_until") or "load").strip().lower()
        if wait_until not in {"load", "domcontentloaded", "networkidle"}:
            wait_until = "load"
        playwright = await _start_playwright()
        if self.policy.browser_backend != "playwright":
            await playwright.stop()
            raise RuntimeError(f"unsupported browser backend: {self.policy.browser_backend}")
        browser_launcher = getattr(playwright, self.policy.browser_name, None)
        if browser_launcher is None:
            await playwright.stop()
            raise RuntimeError(f"unsupported browser name: {self.policy.browser_name}")
        browser = await browser_launcher.launch(headless=self.policy.browser_headless)
        browser_context = await browser.new_context(
            viewport=viewport,
            user_agent=self.policy.user_agent,
            ignore_https_errors=False,
        )
        try:
            await browser_context.add_init_script(
                """
                (() => {
                  window.__aiPlatformBrowserLogs = [];
                  window.__aiPlatformNetworkErrors = [];
                  const pushLog = (entry) => {
                    window.__aiPlatformBrowserLogs.push(entry);
                    if (window.__aiPlatformBrowserLogs.length > 50) window.__aiPlatformBrowserLogs.shift();
                  };
                  ['log', 'info', 'warn', 'error', 'debug'].forEach((method) => {
                    const original = console[method];
                    console[method] = (...args) => {
                      try {
                        pushLog({ type: 'console', level: method, text: args.map(String).join(' '), timestamp: new Date().toISOString() });
                      } catch (error) {}
                      return original.apply(console, args);
                    };
                  });
                  window.addEventListener('error', (event) => {
                    pushLog({ type: 'window_error', level: 'error', text: event.message || 'window error', timestamp: new Date().toISOString() });
                  });
                  window.addEventListener('unhandledrejection', (event) => {
                    pushLog({ type: 'unhandledrejection', level: 'error', text: String(event.reason || 'unhandled rejection'), timestamp: new Date().toISOString() });
                  });
                })();
                """
            )
        except Exception:
            pass
        session_id = f"browser-session-{hashlib.sha256(os.urandom(16)).hexdigest()[:24]}"
        page = await browser_context.new_page()
        pending_console_messages: list[dict[str, Any]] = []
        pending_network_errors: list[dict[str, Any]] = []
        if hasattr(page, "on"):
            page.on(
                "console",
                lambda message: pending_console_messages.append(
                    {
                        "type": "console",
                        "level": _short_text(getattr(message, "type", ""), 32) or "log",
                        "text": _short_text(getattr(message, "text", ""), 500),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                ),
            )
            page.on(
                "requestfailed",
                lambda request: pending_network_errors.append(
                    {
                        "url": _short_text(getattr(request, "url", ""), 500),
                        "method": _short_text(getattr(request, "method", ""), 16),
                        "text": _short_text(_request_failure_text(request), 500) or "request failed",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                ),
            )
        try:
            response = await page.goto(url, wait_until=wait_until, timeout=timeout_ms)
            self._validate_url(str(getattr(page, "url", "") or url))
        except Exception:
            await browser_context.close()
            await browser.close()
            await playwright.stop()
            raise
        title = await _safe_page_title(page)
        now = time.monotonic()
        self.sessions[session_id] = BrowserSession(
            session_id=session_id,
            url=str(getattr(page, "url", "") or url),
            title=title,
            playwright=playwright,
            browser=browser,
            context=browser_context,
            page=page,
            created_at=now,
            updated_at=now,
            viewport=viewport,
            console_messages=pending_console_messages[-50:],
            network_errors=pending_network_errors[-50:],
        )
        snapshot = await self._snapshot_payload(self.sessions[session_id], max_chars=arguments.get("max_chars"))
        return {
            "status": "completed",
            "session_id": session_id,
            "url": snapshot.get("url"),
            "requested_url": url,
            "title": snapshot.get("title"),
            "http_status": response.status if response is not None else None,
            "captured_at": snapshot.get("captured_at"),
            "viewport": viewport,
            "text": snapshot.get("text"),
            "console_messages": snapshot.get("console_messages"),
            "network_errors": snapshot.get("network_errors"),
            "truncated": snapshot.get("truncated"),
            "source": "browser_open",
        }


class BrowserClickTool(BrowserTool):
    spec = ToolSpec(
        name="browser_click",
        description="Click a selector in an existing browser session and return the updated page snapshot.",
        input_schema={
            "type": "object",
            "required": ["session_id", "selector"],
            "properties": {
                "session_id": {"type": "string"},
                "selector": {"type": "string"},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 60},
                "max_chars": {"type": "integer", "minimum": 100, "maximum": 100000},
            },
        },
        kind="web",
        metadata=_tool_metadata(available=False, capability="browser_verify", risk_level="high"),
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            self._validate_browser_available()
        except RuntimeError as exc:
            return self._browser_failure_result("browser_unavailable", message=str(exc))
        await self._reap_stale_sessions()
        try:
            session = self._get_session(arguments.get("session_id"))
        except ValueError as exc:
            return self._browser_failure_result("unknown_session", message=str(exc), status="not_found")
        selector = str(arguments.get("selector") or "").strip()
        if not selector:
            raise ValueError("selector is required")
        timeout_ms = _clamp_int(arguments.get("timeout_seconds"), default=10, minimum=1, maximum=60) * 1000
        await session.page.click(selector, timeout=timeout_ms)
        snapshot = await self._snapshot_payload(session, max_chars=arguments.get("max_chars"))
        return {
            "status": "completed",
            "action": "click",
            "selector": selector,
            **snapshot,
        }


class BrowserTypeTool(BrowserTool):
    spec = ToolSpec(
        name="browser_type",
        description="Fill or type text into a selector in an existing browser session and return the updated page snapshot.",
        input_schema={
            "type": "object",
            "required": ["session_id", "selector", "text"],
            "properties": {
                "session_id": {"type": "string"},
                "selector": {"type": "string"},
                "text": {"type": "string"},
                "submit": {"type": "boolean", "default": False},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 60},
                "max_chars": {"type": "integer", "minimum": 100, "maximum": 100000},
            },
        },
        kind="web",
        metadata=_tool_metadata(available=False, capability="browser_verify", risk_level="high"),
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            self._validate_browser_available()
        except RuntimeError as exc:
            return self._browser_failure_result("browser_unavailable", message=str(exc))
        await self._reap_stale_sessions()
        try:
            session = self._get_session(arguments.get("session_id"))
        except ValueError as exc:
            return self._browser_failure_result("unknown_session", message=str(exc), status="not_found")
        selector = str(arguments.get("selector") or "").strip()
        if not selector:
            raise ValueError("selector is required")
        text = str(arguments.get("text") or "")
        timeout_ms = _clamp_int(arguments.get("timeout_seconds"), default=10, minimum=1, maximum=60) * 1000
        await session.page.fill(selector, text, timeout=timeout_ms)
        if bool(arguments.get("submit", False)):
            await session.page.press(selector, "Enter", timeout=timeout_ms)
        snapshot = await self._snapshot_payload(session, max_chars=arguments.get("max_chars"))
        return {
            "status": "completed",
            "action": "type",
            "selector": selector,
            "submitted": bool(arguments.get("submit", False)),
            **snapshot,
        }


class BrowserScreenshotTool(BrowserTool):
    spec = ToolSpec(
        name="browser_screenshot",
        description="Capture a PNG screenshot from an existing browser session and return it as a media artifact payload.",
        input_schema={
            "type": "object",
            "required": ["session_id"],
            "properties": {
                "session_id": {"type": "string"},
                "full_page": {"type": "boolean", "default": True},
            },
        },
        kind="web",
        metadata=_tool_metadata(available=False, capability="browser_verify", risk_level="high"),
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            self._validate_browser_available()
        except RuntimeError as exc:
            return self._browser_failure_result("browser_unavailable", message=str(exc))
        await self._reap_stale_sessions()
        try:
            session = self._get_session(arguments.get("session_id"))
        except ValueError as exc:
            return self._browser_failure_result("unknown_session", message=str(exc), status="not_found")
        data = await session.page.screenshot(type="png", full_page=bool(arguments.get("full_page", True)))
        title = await _safe_page_title(session.page)
        url = str(getattr(session.page, "url", "") or session.url)
        captured_at = datetime.now(timezone.utc).isoformat()
        image = {
            "title": title or "Browser Screenshot",
            "path": f"{session.session_id}.png",
            "mime_type": "image/png",
            "size_bytes": len(data),
            "source_url": url,
            "data": base64.b64encode(data).decode("ascii"),
            "description": f"Screenshot captured from {url}",
            "metadata": {
                "session_id": session.session_id,
                "captured_at": captured_at,
                "viewport": session.viewport,
                "full_page": bool(arguments.get("full_page", True)),
            },
        }
        session.updated_at = time.monotonic()
        return {
            "status": "completed",
            "session_id": session.session_id,
            "url": url,
            "title": title,
            "captured_at": captured_at,
            "images": [image],
            "source": "browser_screenshot",
        }


class BrowserSnapshotTool(BrowserTool):
    spec = ToolSpec(
        name="browser_snapshot",
        description="Capture normalized DOM text and bounded HTML from an existing browser session.",
        input_schema={
            "type": "object",
            "required": ["session_id"],
            "properties": {
                "session_id": {"type": "string"},
                "max_chars": {"type": "integer", "minimum": 100, "maximum": 100000},
            },
        },
        kind="web",
        metadata=_tool_metadata(available=False, capability="browser_verify", risk_level="medium"),
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            self._validate_browser_available()
        except RuntimeError as exc:
            return self._browser_failure_result("browser_unavailable", message=str(exc))
        await self._reap_stale_sessions()
        try:
            session = self._get_session(arguments.get("session_id"))
        except ValueError as exc:
            return self._browser_failure_result("unknown_session", message=str(exc), status="not_found")
        result = {
            "status": "completed",
            **await self._snapshot_payload(session, max_chars=arguments.get("max_chars")),
        }
        session.updated_at = time.monotonic()
        return result


class BrowserCloseTool(BrowserTool):
    spec = ToolSpec(
        name="browser_close",
        description="Close a managed browser session and release its browser runtime resources.",
        input_schema={
            "type": "object",
            "required": ["session_id"],
            "properties": {"session_id": {"type": "string"}},
        },
        kind="web",
        metadata=_tool_metadata(available=False, capability="browser_verify", risk_level="medium"),
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            self._validate_browser_available()
        except RuntimeError as exc:
            return self._browser_failure_result("browser_unavailable", message=str(exc))
        await self._reap_stale_sessions()
        session_id = str(arguments.get("session_id") or "").strip()
        if not session_id:
            raise ValueError("session_id is required")
        closed = await self._close_session(session_id)
        if not closed:
            return {
                "status": "not_found",
                "session_id": session_id,
                "closed": False,
                "failure_category": "unknown_session",
                "recovery": self._failure_recovery("unknown_session", message="browser session was not found"),
                "source": "browser_close",
            }
        return {
            "status": "completed",
            "session_id": session_id,
            "closed": closed,
            "source": "browser_close",
        }


class BrowserVerifyTool(BrowserTool):
    spec = ToolSpec(
        name="browser_verify",
        description="Open a page, capture a browser snapshot, and include console and network diagnostics in one call.",
        input_schema={
            "type": "object",
            "required": ["url"],
            "properties": {
                "url": {"type": "string"},
                "width": {"type": "integer", "minimum": 320, "maximum": 3840},
                "height": {"type": "integer", "minimum": 240, "maximum": 2160},
                "wait_until": {"type": "string", "enum": ["load", "domcontentloaded", "networkidle"]},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 120},
                "max_chars": {"type": "integer", "minimum": 100, "maximum": 100000},
            },
        },
        kind="web",
        metadata=_tool_metadata(available=False, capability="browser_verify", risk_level="high"),
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        await self._reap_stale_sessions()
        open_result = await BrowserOpenTool(self.policy, self.sessions).execute(context, arguments)
        if open_result.get("status") != "completed":
            return {**open_result, "source": "browser_verify"}
        session = self._get_session(open_result["session_id"])
        snapshot = await self._snapshot_payload(session, max_chars=arguments.get("max_chars"))
        return {
            "status": "completed",
            "verification": {
                "session_id": session.session_id,
                "url": snapshot.get("url"),
                "title": snapshot.get("title"),
                "has_console_errors": any(item.get("level") == "error" for item in snapshot.get("console_messages", [])),
                "has_network_errors": bool(snapshot.get("network_errors")),
                "console_message_count": len(snapshot.get("console_messages", [])),
                "network_error_count": len(snapshot.get("network_errors", [])),
            },
            **snapshot,
            "source": "browser_verify",
        }


class PDFExtractTool(WebTool):
    spec = ToolSpec(
        name="pdf_extract",
        description="Download a policy-allowed PDF and extract bounded page text with source metadata.",
        input_schema={
            "type": "object",
            "required": ["url"],
            "properties": {
                "url": {"type": "string"},
                "max_bytes": {"type": "integer", "minimum": 1000, "maximum": 20000000},
                "max_pages": {"type": "integer", "minimum": 1, "maximum": 100},
                "max_chars": {"type": "integer", "minimum": 100, "maximum": 100000},
            },
        },
        kind="web",
        metadata=_tool_metadata(available=False, capability="browser_verify", risk_level="medium"),
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        downloaded = await self._download(str(arguments.get("url") or ""), max_bytes=arguments.get("max_bytes"))
        data = downloaded.pop("data", b"")
        content_type = str(downloaded.get("headers", {}).get("content_type") or "").split(";", 1)[0].strip()
        if downloaded.get("error"):
            return {**downloaded, "content_type": content_type, "pages": [], "source": "pdf_extract"}
        if content_type and content_type != "application/pdf":
            raise ValueError(f"content type is not a PDF: {content_type}")
        try:
            from PyPDF2 import PdfReader
        except ImportError as exc:
            return {
                "status": "failed",
                "url": downloaded.get("url"),
                "requested_url": downloaded.get("requested_url"),
                "filename": downloaded.get("filename"),
                "content_type": content_type or "application/pdf",
                "bytes": downloaded.get("bytes") or 0,
                "sha256": downloaded.get("sha256"),
                "pages": [],
                "failure_category": "pdf_dependency_missing",
                "error": "PyPDF2 is required for pdf_extract",
                "recovery": self._failure_recovery("pdf_dependency_missing"),
                "source": "pdf_extract",
            }
        try:
            reader = PdfReader(BytesIO(data))
        except Exception as exc:
            message = str(exc) or "failed to parse PDF"
            return {
                "status": "failed",
                "url": downloaded.get("url"),
                "requested_url": downloaded.get("requested_url"),
                "filename": downloaded.get("filename"),
                "content_type": content_type or "application/pdf",
                "bytes": downloaded.get("bytes") or 0,
                "sha256": downloaded.get("sha256"),
                "pages": [],
                "failure_category": "parse_error",
                "error": message,
                "recovery": self._failure_recovery("parse_error", message=message),
                "source": "pdf_extract",
            }
        max_pages = _clamp_int(arguments.get("max_pages"), default=self.policy.pdf_max_pages, minimum=1, maximum=self.policy.pdf_max_pages)
        max_chars = _clamp_int(arguments.get("max_chars"), default=self.policy.max_output_chars, minimum=100, maximum=self.policy.max_output_chars)
        pages: list[dict[str, Any]] = []
        consumed_chars = 0
        for index, page in enumerate(reader.pages[:max_pages]):
            text = page.extract_text() or ""
            remaining = max_chars - consumed_chars
            if remaining <= 0:
                break
            page_text, text_truncated = self._truncate_text(text, remaining)
            consumed_chars += len(page_text)
            pages.append(
                {
                    "page_number": index + 1,
                    "text": page_text,
                    "truncated": text_truncated,
                    "source": downloaded.get("url") or downloaded.get("requested_url"),
                    "metadata": {
                        "filename": downloaded.get("filename"),
                        "sha256": downloaded.get("sha256"),
                    },
                }
            )
        return {
            "status": downloaded.get("status"),
            "url": downloaded.get("url"),
            "requested_url": downloaded.get("requested_url"),
            "filename": downloaded.get("filename"),
            "content_type": content_type or "application/pdf",
            "bytes": downloaded.get("bytes") or 0,
            "sha256": downloaded.get("sha256"),
            "fetched_at": downloaded.get("fetched_at"),
            "page_count": len(reader.pages),
            "extracted_pages": len(pages),
            "pages": pages,
            "truncated": bool(downloaded.get("truncated")) or len(reader.pages) > len(pages) or consumed_chars >= max_chars,
            "source": "pdf_extract",
        }


WEB_TOOL_TYPES = {
    "fetch_url": FetchURLTool,
    "open_page": OpenPageTool,
    "extract_page_text": ExtractPageTextTool,
    "web_search": WebSearchTool,
    "download_file": DownloadFileTool,
    "browser_open": BrowserOpenTool,
    "browser_click": BrowserClickTool,
    "browser_type": BrowserTypeTool,
    "browser_screenshot": BrowserScreenshotTool,
    "browser_snapshot": BrowserSnapshotTool,
    "browser_close": BrowserCloseTool,
    "browser_verify": BrowserVerifyTool,
    "pdf_extract": PDFExtractTool,
}


class WebToolProvider:
    def __init__(
        self,
        *,
        enabled_tool_names: Sequence[str],
        network_configured: bool = False,
        allowed_domains: Sequence[str] | None = None,
        denied_domains: Sequence[str] | None = None,
        allowed_content_types: Sequence[str] | None = None,
        allowed_download_content_types: Sequence[str] | None = None,
        max_response_bytes: int = 1_000_000,
        max_download_bytes: int = 2_000_000,
        max_output_chars: int = 40_000,
        timeout_seconds: int = 20,
        user_agent: str = "AI-Platform-Agent/1.0",
        search_endpoint: str | None = None,
        browser_configured: bool = False,
        browser_enabled: bool = False,
        browser_backend: str = "playwright",
        browser_name: str = "chromium",
        browser_headless: bool = True,
        browser_max_sessions: int = 4,
        browser_session_ttl_seconds: int = 900,
        browser_snapshot_chars: int = 60_000,
        pdf_max_pages: int = 20,
        search_require_url: bool = True,
        search_require_title: bool = True,
        search_require_snippet: bool = False,
        search_allowed_schemes: Sequence[str] | None = None,
        search_reject_disallowed_domains: bool = True,
        search_reject_duplicates: bool = True,
    ) -> None:
        enabled_browser_tools = set(DEFAULT_BROWSER_TOOL_NAMES) if browser_enabled else set()
        self.enabled_tool_names = [
            name
            for name in enabled_tool_names
            if name in WEB_TOOL_TYPES and (name not in DEFAULT_BROWSER_TOOL_NAMES or name in enabled_browser_tools)
        ]
        self.browser_sessions: dict[str, BrowserSession] = {}
        self.policy = WebPolicy(
            network_configured=network_configured,
            allowed_domains=tuple(allowed_domains or ()),
            denied_domains=tuple(denied_domains or ()),
            allowed_content_types=tuple(allowed_content_types or DEFAULT_ALLOWED_CONTENT_TYPES),
            allowed_download_content_types=tuple(allowed_download_content_types or DEFAULT_DOWNLOAD_CONTENT_TYPES),
            max_response_bytes=max_response_bytes,
            max_download_bytes=max_download_bytes,
            max_output_chars=max_output_chars,
            timeout_seconds=timeout_seconds,
            user_agent=user_agent,
            search_endpoint=str(search_endpoint or "").strip() or None,
            browser_configured=browser_configured,
            browser_backend=str(browser_backend or "playwright").strip() or "playwright",
            browser_name=str(browser_name or "chromium").strip().lower() or "chromium",
            browser_headless=browser_headless,
            browser_max_sessions=browser_max_sessions,
            browser_session_ttl_seconds=browser_session_ttl_seconds,
            browser_snapshot_chars=browser_snapshot_chars,
            pdf_max_pages=pdf_max_pages,
            search_require_url=search_require_url,
            search_require_title=search_require_title,
            search_require_snippet=search_require_snippet,
            search_allowed_schemes=tuple(search_allowed_schemes or DEFAULT_SEARCH_ALLOWED_SCHEMES),
            search_reject_disallowed_domains=search_reject_disallowed_domains,
            search_reject_duplicates=search_reject_duplicates,
        )

    @classmethod
    def from_env(cls) -> "WebToolProvider":
        browser_enabled = _env_bool("AGENT_BROWSER_ENABLED", False)
        default_tools = (*DEFAULT_WEB_TOOL_NAMES, *DEFAULT_BROWSER_TOOL_NAMES) if browser_enabled else DEFAULT_WEB_TOOL_NAMES
        return cls(
            enabled_tool_names=_parse_csv(os.getenv("AGENT_WEB_TOOLS"), default_tools),
            network_configured=_env_bool("AGENT_WEB_NETWORK_CONFIGURED", False),
            allowed_domains=_parse_csv(os.getenv("AGENT_WEB_ALLOWED_DOMAINS"), ()),
            denied_domains=_parse_csv(os.getenv("AGENT_WEB_DENIED_DOMAINS"), ()),
            allowed_content_types=_parse_csv(os.getenv("AGENT_WEB_ALLOWED_CONTENT_TYPES"), DEFAULT_ALLOWED_CONTENT_TYPES),
            allowed_download_content_types=_parse_csv(os.getenv("AGENT_WEB_ALLOWED_DOWNLOAD_CONTENT_TYPES"), DEFAULT_DOWNLOAD_CONTENT_TYPES),
            max_response_bytes=_clamp_int(os.getenv("AGENT_WEB_MAX_RESPONSE_BYTES"), default=1_000_000, minimum=1_000, maximum=5_000_000),
            max_download_bytes=_clamp_int(os.getenv("AGENT_WEB_MAX_DOWNLOAD_BYTES"), default=2_000_000, minimum=1_000, maximum=20_000_000),
            max_output_chars=_clamp_int(os.getenv("AGENT_WEB_MAX_OUTPUT_CHARS"), default=40_000, minimum=100, maximum=200_000),
            timeout_seconds=_clamp_int(os.getenv("AGENT_WEB_TIMEOUT_SECONDS"), default=20, minimum=1, maximum=120),
            user_agent=str(os.getenv("AGENT_WEB_USER_AGENT") or "AI-Platform-Agent/1.0").strip() or "AI-Platform-Agent/1.0",
            search_endpoint=os.getenv("AGENT_WEB_SEARCH_ENDPOINT"),
            browser_enabled=browser_enabled,
            browser_configured=_env_bool("AGENT_BROWSER_CONFIGURED", False),
            browser_backend=str(os.getenv("AGENT_BROWSER_BACKEND") or "playwright").strip() or "playwright",
            browser_name=str(os.getenv("AGENT_BROWSER_NAME") or "chromium").strip().lower() or "chromium",
            browser_headless=_env_bool("AGENT_BROWSER_HEADLESS", True),
            browser_max_sessions=_clamp_int(os.getenv("AGENT_BROWSER_MAX_SESSIONS"), default=4, minimum=1, maximum=32),
            browser_session_ttl_seconds=_clamp_int(
                os.getenv("AGENT_BROWSER_SESSION_TTL_SECONDS"),
                default=900,
                minimum=60,
                maximum=86_400,
            ),
            browser_snapshot_chars=_clamp_int(os.getenv("AGENT_BROWSER_SNAPSHOT_CHARS"), default=60_000, minimum=500, maximum=200_000),
            pdf_max_pages=_clamp_int(os.getenv("AGENT_PDF_MAX_PAGES"), default=20, minimum=1, maximum=100),
            search_require_url=_env_bool("AGENT_WEB_SEARCH_REQUIRE_URL", True),
            search_require_title=_env_bool("AGENT_WEB_SEARCH_REQUIRE_TITLE", True),
            search_require_snippet=_env_bool("AGENT_WEB_SEARCH_REQUIRE_SNIPPET", False),
            search_allowed_schemes=tuple(
                item.lower() for item in _parse_csv(os.getenv("AGENT_WEB_SEARCH_ALLOWED_SCHEMES"), DEFAULT_SEARCH_ALLOWED_SCHEMES)
            ),
            search_reject_disallowed_domains=_env_bool("AGENT_WEB_SEARCH_REJECT_DISALLOWED_DOMAINS", True),
            search_reject_duplicates=_env_bool("AGENT_WEB_SEARCH_REJECT_DUPLICATES", True),
        )

    def _build_tool(self, name: str, context: ToolLookupContext | None = None) -> BaseTool | None:
        if not self.policy.network_configured:
            return None
        tool_type = WEB_TOOL_TYPES.get(name)
        if tool_type is None or name not in self.enabled_tool_names:
            return None
        if name in DEFAULT_BROWSER_TOOL_NAMES:
            if name == "pdf_extract":
                return tool_type(self.policy)
            return tool_type(self.policy, self.browser_sessions)
        return tool_type(self.policy)

    async def get(self, name: str, context: ToolLookupContext | None = None) -> BaseTool | None:
        return self._build_tool(name, context=context)

    async def get_spec(self, name: str, context: ToolLookupContext | None = None) -> dict | None:
        tool = self._build_tool(name, context=context)
        if tool is None:
            return None
        if isinstance(tool, WebTool):
            return tool.spec_dict()
        return {
            "name": tool.spec.name,
            "description": tool.spec.description,
            "input_schema": tool.spec.input_schema,
            "kind": tool.spec.kind,
            "metadata": tool.spec.metadata,
        }

    async def list_specs(self, context: ToolLookupContext | None = None) -> list[dict]:
        items = []
        for name in self.enabled_tool_names:
            spec = await self.get_spec(name, context=context)
            if spec is not None:
                items.append(spec)
        return items

    def browser_session_snapshot(self) -> dict[str, Any]:
        return BrowserTool(self.policy, self.browser_sessions).browser_session_snapshot()

    async def browser_session_summary(self) -> dict[str, Any]:
        return await BrowserTool(self.policy, self.browser_sessions).browser_session_summary()
