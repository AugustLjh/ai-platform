import base64
import json
import time

import pytest

from ai_runtime.core.agent_runtime.tools.base import ToolContext, ToolLookupContext
from ai_runtime.core.agent_runtime.tools.providers.web import BrowserSession, WebToolProvider


def _context() -> ToolContext:
    return ToolContext(
        run_id="run-1",
        tenant_id="tenant-1",
        user_id="user-1",
        agent_definition_id="agent-1",
    )


async def test_web_provider_hides_tools_until_network_is_configured():
    provider = WebToolProvider(enabled_tool_names=["fetch_url", "open_page"], network_configured=False)

    specs = await provider.list_specs(ToolLookupContext(tenant_id="tenant-1"))

    assert specs == []
    assert await provider.get("fetch_url", context=None) is None


async def test_web_provider_exposes_policy_metadata_when_configured():
    provider = WebToolProvider(enabled_tool_names=["fetch_url", "web_search", "download_file"], network_configured=True)

    specs = await provider.list_specs(ToolLookupContext(tenant_id="tenant-1"))
    metadata_by_name = {spec["name"]: spec["metadata"] for spec in specs}

    assert {"fetch_url", "web_search", "download_file"} == set(metadata_by_name)
    assert metadata_by_name["fetch_url"]["provider"] == "web"
    assert metadata_by_name["fetch_url"]["capability"] == "web_research"
    assert metadata_by_name["fetch_url"]["access_level"] == "network"
    assert metadata_by_name["fetch_url"]["side_effect"] == "network"
    assert metadata_by_name["fetch_url"]["requires_workspace"] is False
    assert metadata_by_name["fetch_url"]["failure_taxonomy"]["provider"] == "web"
    assert {
        item["category"] for item in metadata_by_name["fetch_url"]["failure_taxonomy"]["categories"]
    } >= {"timeout", "network_error", "content_type_denied", "search_no_results", "unknown_session"}
    assert metadata_by_name["download_file"]["risk_level"] == "high"


async def test_web_provider_prefers_env_tool_list(monkeypatch):
    monkeypatch.setenv("AGENT_WEB_TOOLS", "open_page")
    monkeypatch.setenv("AGENT_WEB_NETWORK_CONFIGURED", "true")
    monkeypatch.setenv("AGENT_WEB_ALLOWED_DOMAINS", "example.test")

    provider = WebToolProvider.from_env()
    specs = await provider.list_specs(ToolLookupContext(tenant_id="tenant-1"))

    assert [spec["name"] for spec in specs] == ["open_page"]
    assert provider.policy.allowed_domains == ("example.test",)


async def test_browser_tools_require_explicit_browser_enablement(monkeypatch):
    monkeypatch.setenv("AGENT_WEB_NETWORK_CONFIGURED", "true")
    monkeypatch.delenv("AGENT_BROWSER_ENABLED", raising=False)

    provider = WebToolProvider.from_env()
    specs = await provider.list_specs(ToolLookupContext(tenant_id="tenant-1"))

    assert "browser_open" not in {spec["name"] for spec in specs}


async def test_browser_tools_expose_browser_verify_metadata_when_enabled(monkeypatch):
    monkeypatch.setattr(
        "ai_runtime.core.agent_runtime.tools.providers.web._browser_runtime_status",
        lambda: (True, "browser runtime is available"),
    )
    provider = WebToolProvider(
        enabled_tool_names=["browser_open", "browser_snapshot", "browser_close", "browser_verify", "pdf_extract"],
        network_configured=True,
        browser_enabled=True,
        browser_configured=True,
    )

    specs = await provider.list_specs(ToolLookupContext(tenant_id="tenant-1"))
    metadata_by_name = {spec["name"]: spec["metadata"] for spec in specs}

    assert {"browser_open", "browser_snapshot", "browser_close", "browser_verify", "pdf_extract"} == set(metadata_by_name)
    assert metadata_by_name["browser_open"]["provider"] == "web"
    assert metadata_by_name["browser_open"]["capability"] == "browser_verify"
    assert metadata_by_name["browser_open"]["requires_browser"] is True
    assert metadata_by_name["browser_snapshot"]["risk_level"] == "medium"
    assert metadata_by_name["browser_verify"]["capability"] == "browser_verify"


async def test_browser_tool_metadata_reports_missing_runtime(monkeypatch):
    monkeypatch.setattr(
        "ai_runtime.core.agent_runtime.tools.providers.web._browser_runtime_status",
        lambda: (False, "playwright is not installed"),
    )
    provider = WebToolProvider(
        enabled_tool_names=["browser_open"],
        network_configured=True,
        browser_enabled=True,
        browser_configured=True,
    )

    specs = await provider.list_specs(ToolLookupContext(tenant_id="tenant-1"))

    assert specs[0]["name"] == "browser_open"
    assert specs[0]["metadata"]["status"] == "unavailable"
    assert specs[0]["metadata"]["unavailable_reason"] == "playwright is not installed"
    assert specs[0]["metadata"]["failure_taxonomy"]["provider"] == "web"


async def test_fetch_url_rejects_disallowed_domain():
    provider = WebToolProvider(
        enabled_tool_names=["fetch_url"],
        network_configured=True,
        allowed_domains=["docs.example.com"],
    )
    tool = await provider.get("fetch_url", context=ToolLookupContext(tenant_id="tenant-1"))
    assert tool is not None

    with pytest.raises(PermissionError):
        await tool.execute(_context(), {"url": "https://evil.example.net/page"})


async def test_open_page_extracts_readable_text():
    provider = WebToolProvider(
        enabled_tool_names=["open_page"],
        network_configured=True,
        allowed_domains=["docs.example.com"],
    )
    tool = await provider.get("open_page", context=ToolLookupContext(tenant_id="tenant-1"))
    assert tool is not None

    async def fake_fetch(url, *, max_bytes=None):
        return {
            "url": url,
            "requested_url": url,
            "status": 200,
            "headers": {"content_type": "text/html"},
            "text": "<html><head><title>Runtime Docs</title><script>hide()</script></head><body><h1>Guide</h1><p>Use artifacts.</p></body></html>",
            "truncated": False,
            "fetched_at": "2026-05-14T00:00:00+00:00",
        }

    tool._fetch = fake_fetch
    result = await tool.execute(_context(), {"url": "https://docs.example.com/docs"})

    assert result["status"] == 200
    assert result["title"] == "Runtime Docs"
    assert "Guide" in result["text"]
    assert "Use artifacts." in result["text"]
    assert "hide()" not in result["text"]
    assert result["source"] == "web"


async def test_web_search_uses_configured_json_endpoint():
    provider = WebToolProvider(
        enabled_tool_names=["web_search"],
        network_configured=True,
        allowed_domains=["search.example.com", "docs.example.com"],
        search_endpoint="https://search.example.com/search",
    )
    tool = await provider.get("web_search", context=ToolLookupContext(tenant_id="tenant-1"))
    assert tool is not None

    async def fake_fetch(url, *, max_bytes=None):
        assert "q=runtime" in url
        assert "limit=2" in url
        return {
            "url": url,
            "requested_url": url,
            "status": 200,
            "headers": {"content_type": "application/json"},
            "text": json.dumps(
                {
                    "items": [
                        {"title": "Runtime Plan", "url": "https://docs.example.com/runtime", "snippet": "Use web artifacts."},
                        {"title": "Sandbox Plan", "url": "https://docs.example.com/sandbox", "snippet": "Verify in sandbox."},
                    ]
                }
            ),
            "truncated": False,
            "fetched_at": "2026-05-14T00:00:00+00:00",
        }

    tool._fetch = fake_fetch
    result = await tool.execute(_context(), {"query": "runtime", "limit": 2})

    assert result["query"] == "runtime"
    assert result["total"] == 2
    assert result["items"][0]["title"] == "Runtime Plan"
    assert result["quality"]["status"] == "accepted"
    assert result["quality"]["accepted_count"] == 2


async def test_web_search_applies_result_quality_rules():
    provider = WebToolProvider(
        enabled_tool_names=["web_search"],
        network_configured=True,
        allowed_domains=["search.example.com", "docs.example.com"],
        search_endpoint="https://search.example.com/search",
    )
    tool = await provider.get("web_search", context=ToolLookupContext(tenant_id="tenant-1"))
    assert tool is not None

    async def fake_fetch(url, *, max_bytes=None):
        return {
            "url": url,
            "requested_url": url,
            "status": 200,
            "headers": {"content_type": "application/json"},
            "text": json.dumps(
                {
                    "items": [
                        {"title": "Runtime Plan", "url": "https://docs.example.com/runtime", "snippet": "Use web artifacts."},
                        {"title": "Runtime Plan", "url": "https://docs.example.com/runtime", "snippet": "Duplicate result."},
                        {"title": "", "url": "https://evil.example.net/bad", "snippet": "Denied domain."},
                        {"title": "Missing URL", "snippet": "Rejected."},
                    ]
                }
            ),
            "truncated": False,
            "fetched_at": "2026-05-14T00:00:00+00:00",
        }

    tool._fetch = fake_fetch
    result = await tool.execute(_context(), {"query": "runtime", "limit": 4})

    assert result["total"] == 1
    assert result["accepted"][0]["title"] == "Runtime Plan"
    assert result["rejected_count"] == 3
    assert result["quality"]["rejected_count"] == 3
    assert result["quality"]["rules"]["reject_duplicates"] is True


async def test_web_search_no_accepted_results_returns_recovery_guidance():
    provider = WebToolProvider(
        enabled_tool_names=["web_search"],
        network_configured=True,
        allowed_domains=["search.example.com", "docs.example.com"],
        search_endpoint="https://search.example.com/search",
    )
    tool = await provider.get("web_search", context=ToolLookupContext(tenant_id="tenant-1"))
    assert tool is not None

    async def fake_fetch(url, *, max_bytes=None):
        return {
            "url": url,
            "requested_url": url,
            "status": 200,
            "headers": {"content_type": "application/json"},
            "text": json.dumps({"items": [{"title": "", "url": "", "snippet": "missing url and title"}]}),
            "truncated": False,
            "fetched_at": "2026-05-14T00:00:00+00:00",
        }

    tool._fetch = fake_fetch
    result = await tool.execute(_context(), {"query": "runtime", "limit": 1})

    assert result["quality"]["status"] == "warning"
    assert result["failure_category"] == "search_no_results"
    assert result["recovery"]["primary_code"] == "web_search_no_results"


async def test_download_file_returns_bounded_file_artifact_payload():
    provider = WebToolProvider(
        enabled_tool_names=["download_file"],
        network_configured=True,
        allowed_domains=["files.example.com"],
        max_download_bytes=1000,
    )
    tool = await provider.get("download_file", context=ToolLookupContext(tenant_id="tenant-1"))
    assert tool is not None

    async def fake_download(url, *, max_bytes=None):
        assert max_bytes == 1000
        return {
            "url": url,
            "requested_url": url,
            "status": 200,
            "headers": {"content_type": "application/pdf", "content_length": "11"},
            "filename": "guide.pdf",
            "bytes": 11,
            "sha256": "hash",
            "data": b"hello world",
            "truncated": False,
            "fetched_at": "2026-05-14T00:00:00+00:00",
        }

    tool._download = fake_download
    result = await tool.execute(_context(), {"url": "https://files.example.com/guide.pdf", "max_bytes": 1000})

    assert result["filename"] == "guide.pdf"
    assert result["content_type"] == "application/pdf"
    assert result["bytes"] == 11
    assert result["files"][0]["name"] == "guide.pdf"
    assert result["files"][0]["data"] == "aGVsbG8gd29ybGQ="
    assert result["files"][0]["metadata"]["sha256"] == "hash"


async def test_download_file_rejects_disallowed_download_content_type():
    provider = WebToolProvider(
        enabled_tool_names=["download_file"],
        network_configured=True,
        allowed_domains=["files.example.com"],
        allowed_download_content_types=["application/pdf"],
    )
    tool = await provider.get("download_file", context=ToolLookupContext(tenant_id="tenant-1"))
    assert tool is not None

    assert tool._download_content_type_allowed("application/pdf") is True
    assert tool._download_content_type_allowed("application/x-msdownload") is False


async def test_download_file_content_type_denied_returns_recovery_payload():
    provider = WebToolProvider(
        enabled_tool_names=["download_file"],
        network_configured=True,
        allowed_domains=["files.example.com"],
        allowed_download_content_types=["application/pdf"],
    )
    tool = await provider.get("download_file", context=ToolLookupContext(tenant_id="tenant-1"))
    assert tool is not None

    async def fake_download(url, *, max_bytes=None):
        return {
            "url": url,
            "requested_url": url,
            "status": 200,
            "headers": {"content_type": "application/x-msdownload", "content_length": "10"},
            "filename": "setup.exe",
            "bytes": 0,
            "sha256": "",
            "data": b"",
            "truncated": False,
            "fetched_at": "2026-05-14T00:00:00+00:00",
            "failure_category": "content_type_denied",
            "error": "content type is not allowed for download: application/x-msdownload",
            "recovery": {
                "primary_code": "web_content_type_denied",
                "failure_category": "content_type_denied",
                "summary": "content type is not allowed for download: application/x-msdownload",
                "severity": "error",
                "recoverable": True,
                "actions": ["Use a URL that returns an allowed content type."],
            },
        }

    tool._download = fake_download
    result = await tool.execute(_context(), {"url": "https://files.example.com/setup.exe"})

    assert result["failure_category"] == "content_type_denied"
    assert result["recovery"]["primary_code"] == "web_content_type_denied"
    assert result["files"][0]["metadata"]["failure_category"] == "content_type_denied"


class _FakeLocator:
    async def inner_text(self, timeout=2000):
        return "Dashboard\nReady"


class _FakePage:
    url = "https://app.example.com/dashboard"

    def __init__(self):
        self.clicked = []
        self.filled = []

    def locator(self, selector):
        assert selector == "body"
        return _FakeLocator()

    async def content(self):
        return "<html><body><main>Dashboard</main></body></html>"

    async def title(self):
        return "Example App"

    async def click(self, selector, timeout=10000):
        self.clicked.append((selector, timeout))

    async def fill(self, selector, text, timeout=10000):
        self.filled.append((selector, text, timeout))

    async def press(self, selector, key, timeout=10000):
        self.filled.append((selector, key, timeout))

    async def screenshot(self, type="png", full_page=True):
        return b"\x89PNG\r\n"


class _FakeCloseable:
    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True


class _FakePlaywright:
    def __init__(self):
        self.stopped = False

    async def stop(self):
        self.stopped = True


async def test_browser_snapshot_uses_existing_session(monkeypatch):
    monkeypatch.setattr(
        "ai_runtime.core.agent_runtime.tools.providers.web._browser_runtime_status",
        lambda: (True, "browser runtime is available"),
    )
    provider = WebToolProvider(
        enabled_tool_names=["browser_snapshot"],
        network_configured=True,
        browser_enabled=True,
        browser_configured=True,
    )
    provider.browser_sessions["browser-session-1"] = BrowserSession(
        session_id="browser-session-1",
        url="https://app.example.com/dashboard",
        title="Example App",
        playwright=None,
        browser=None,
        context=None,
        page=_FakePage(),
        created_at=time.monotonic(),
        updated_at=time.monotonic(),
        viewport={"width": 1280, "height": 720},
    )
    tool = await provider.get("browser_snapshot", context=ToolLookupContext(tenant_id="tenant-1"))
    assert tool is not None

    result = await tool.execute(_context(), {"session_id": "browser-session-1"})

    assert result["status"] == "completed"
    assert result["session_id"] == "browser-session-1"
    assert result["title"] == "Example App"
    assert "Dashboard" in result["text"]
    assert result["source"] == "browser_snapshot"


async def test_browser_snapshot_unknown_session_returns_recovery(monkeypatch):
    monkeypatch.setattr(
        "ai_runtime.core.agent_runtime.tools.providers.web._browser_runtime_status",
        lambda: (True, "browser runtime is available"),
    )
    provider = WebToolProvider(
        enabled_tool_names=["browser_snapshot"],
        network_configured=True,
        browser_enabled=True,
        browser_configured=True,
    )
    tool = await provider.get("browser_snapshot", context=ToolLookupContext(tenant_id="tenant-1"))
    assert tool is not None

    result = await tool.execute(_context(), {"session_id": "missing-session"})

    assert result["status"] == "not_found"
    assert result["failure_category"] == "unknown_session"
    assert result["recovery"]["primary_code"] == "web_unknown_session"


async def test_browser_verify_returns_diagnostics(monkeypatch):
    monkeypatch.setattr(
        "ai_runtime.core.agent_runtime.tools.providers.web._browser_runtime_status",
        lambda: (True, "browser runtime is available"),
    )

    provider = WebToolProvider(
        enabled_tool_names=["browser_verify"],
        network_configured=True,
        browser_enabled=True,
        browser_configured=True,
    )
    tool = await provider.get("browser_verify", context=ToolLookupContext(tenant_id="tenant-1"))
    assert tool is not None

    class _FakePageWithDiagnostics(_FakePage):
        async def evaluate(self, script, arg=None):
            if "BrowserLogs" in script:
                return [{"type": "console", "level": "error", "text": "boom", "timestamp": "2026-05-16T00:00:00+00:00"}]
            return [{"url": "http://example.test", "method": "GET", "text": "net fail", "timestamp": "2026-05-16T00:00:00+00:00"}]

    class _FakeContext:
        async def add_init_script(self, script):
            return None

        async def new_page(self):
            return _FakePageWithDiagnostics()

    class _FakeBrowser:
        async def new_context(self, **kwargs):
            return _FakeContext()

    class _FakeLauncher:
        async def launch(self, headless=True):
            return _FakeBrowser()

    class _FakePlaywrightFactory:
        chromium = _FakeLauncher()

    async def fake_start():
        return _FakePlaywrightFactory()

    monkeypatch.setattr("ai_runtime.core.agent_runtime.tools.providers.web._start_playwright", fake_start)
    async def fake_safe_page_title(page):
        return "Example App"

    monkeypatch.setattr("ai_runtime.core.agent_runtime.tools.providers.web._safe_page_title", fake_safe_page_title)

    async def fake_goto(self, url, wait_until="load", timeout=1000):
        return type("Response", (), {"status": 200})()

    _FakePageWithDiagnostics.goto = fake_goto

    result = await tool.execute(_context(), {"url": "https://app.example.com/dashboard"})

    assert result["source"] == "browser_verify"
    assert result["verification"]["has_console_errors"] is True
    assert result["verification"]["has_network_errors"] is True


async def test_browser_screenshot_returns_media_payload(monkeypatch):
    monkeypatch.setattr(
        "ai_runtime.core.agent_runtime.tools.providers.web._browser_runtime_status",
        lambda: (True, "browser runtime is available"),
    )
    provider = WebToolProvider(
        enabled_tool_names=["browser_screenshot"],
        network_configured=True,
        browser_enabled=True,
        browser_configured=True,
    )
    provider.browser_sessions["browser-session-1"] = BrowserSession(
        session_id="browser-session-1",
        url="https://app.example.com/dashboard",
        title="Example App",
        playwright=None,
        browser=None,
        context=None,
        page=_FakePage(),
        created_at=time.monotonic(),
        updated_at=time.monotonic(),
        viewport={"width": 1280, "height": 720},
    )
    tool = await provider.get("browser_screenshot", context=ToolLookupContext(tenant_id="tenant-1"))
    assert tool is not None

    result = await tool.execute(_context(), {"session_id": "browser-session-1"})

    assert result["status"] == "completed"
    assert result["images"][0]["mime_type"] == "image/png"
    assert result["images"][0]["data"] == base64.b64encode(b"\x89PNG\r\n").decode("ascii")


async def test_browser_close_releases_session_resources(monkeypatch):
    monkeypatch.setattr(
        "ai_runtime.core.agent_runtime.tools.providers.web._browser_runtime_status",
        lambda: (True, "browser runtime is available"),
    )
    provider = WebToolProvider(
        enabled_tool_names=["browser_close"],
        network_configured=True,
        browser_enabled=True,
        browser_configured=True,
    )
    playwright = _FakePlaywright()
    browser_context = _FakeCloseable()
    browser = _FakeCloseable()
    provider.browser_sessions["browser-session-1"] = BrowserSession(
        session_id="browser-session-1",
        url="https://app.example.com/dashboard",
        title="Example App",
        playwright=playwright,
        browser=browser,
        context=browser_context,
        page=_FakePage(),
        created_at=time.monotonic(),
        updated_at=time.monotonic(),
        viewport={"width": 1280, "height": 720},
    )
    tool = await provider.get("browser_close", context=ToolLookupContext(tenant_id="tenant-1"))
    assert tool is not None

    result = await tool.execute(_context(), {"session_id": "browser-session-1"})

    assert result["status"] == "completed"
    assert result["closed"] is True
    assert "browser-session-1" not in provider.browser_sessions
    assert browser_context.closed is True
    assert browser.closed is True
    assert playwright.stopped is True


async def test_browser_session_snapshot_reports_active_and_expired_sessions(monkeypatch):
    monkeypatch.setattr(
        "ai_runtime.core.agent_runtime.tools.providers.web._browser_runtime_status",
        lambda: (True, "browser runtime is available"),
    )
    provider = WebToolProvider(
        enabled_tool_names=["browser_open"],
        network_configured=True,
        browser_enabled=True,
        browser_configured=True,
        browser_session_ttl_seconds=60,
    )
    provider.browser_sessions["browser-session-1"] = BrowserSession(
        session_id="browser-session-1",
        url="https://app.example.com/dashboard",
        title="Example App",
        playwright=None,
        browser=None,
        context=None,
        page=_FakePage(),
        created_at=time.monotonic(),
        updated_at=time.monotonic(),
        viewport={"width": 1280, "height": 720},
    )
    provider.browser_sessions["browser-session-expired"] = BrowserSession(
        session_id="browser-session-expired",
        url="https://app.example.com/old",
        title="Old App",
        playwright=None,
        browser=None,
        context=None,
        page=_FakePage(),
        created_at=time.monotonic() - 120,
        updated_at=time.monotonic() - 120,
        viewport={"width": 1280, "height": 720},
    )

    snapshot = provider.browser_session_snapshot()

    assert snapshot["session_count"] == 2
    assert snapshot["oldest_session_age_seconds"] is not None
    assert snapshot["sessions"][0]["session_id"] == "browser-session-1"
    assert snapshot["sessions"][0]["console_message_count"] == 0


async def test_pdf_extract_returns_document_pages_payload():
    provider = WebToolProvider(
        enabled_tool_names=["pdf_extract"],
        network_configured=True,
        browser_enabled=True,
        browser_configured=False,
        allowed_domains=["files.example.com"],
    )
    tool = await provider.get("pdf_extract", context=ToolLookupContext(tenant_id="tenant-1"))
    assert tool is not None

    class FakePdfPage:
        def extract_text(self):
            return "Hello from PDF"

    class FakePdfReader:
        def __init__(self, stream):
            self.pages = [FakePdfPage()]

    async def fake_download(url, *, max_bytes=None):
        return {
            "url": url,
            "requested_url": url,
            "status": 200,
            "headers": {"content_type": "application/pdf", "content_length": "8"},
            "filename": "guide.pdf",
            "bytes": 8,
            "sha256": "hash",
            "data": b"%PDF-1.4",
            "truncated": False,
            "fetched_at": "2026-05-14T00:00:00+00:00",
        }

    tool._download = fake_download

    from unittest.mock import patch

    with patch("PyPDF2.PdfReader", FakePdfReader):
        result = await tool.execute(_context(), {"url": "https://files.example.com/guide.pdf"})

    assert result["filename"] == "guide.pdf"
    assert result["page_count"] == 1
    assert result["pages"][0]["text"] == "Hello from PDF"
