from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


EXECUTION_MODE_ORDER = (
    "context_only",
    "read_only_workspace",
    "patch_proposal",
    "sandbox_verified",
    "network_research",
)

EXECUTION_MODE_DETAILS: dict[str, dict[str, Any]] = {
    "context_only": {
        "label": "Context Only",
        "summary": "Use only conversation context, uploaded files, mounted documents, knowledge, and MCP tools explicitly exposed by policy.",
        "capabilities": ("project_context", "knowledge", "mcp"),
        "risk_level": "low",
        "recommended_usage": "Use for low-risk analysis, Q&A, retrieval, and policy-constrained external tools without workspace or sandbox side effects.",
    },
    "read_only_workspace": {
        "label": "Read-only Workspace",
        "summary": "Allow read-only workspace and git inspection when a workspace is bound.",
        "capabilities": ("project_context", "knowledge", "mcp", "workspace_read", "git_read"),
        "risk_level": "low",
        "recommended_usage": "Use when the agent must inspect repository structure, read source files, or audit git history without producing patches.",
    },
    "patch_proposal": {
        "label": "Patch Proposal",
        "summary": "Allow workspace patch proposal tools when write policy is available; changes remain reviewable artifacts.",
        "capabilities": ("project_context", "knowledge", "mcp", "workspace_read", "git_read", "workspace_write"),
        "risk_level": "medium",
        "recommended_usage": "Use for implementation tasks that should stop at patch generation and explicit human review before any repository writeback.",
    },
    "sandbox_verified": {
        "label": "Sandbox Verified",
        "summary": "Allow sandbox-backed test, lint, build, and shell verification tools when the sandbox runner is available.",
        "capabilities": (
            "project_context",
            "knowledge",
            "mcp",
            "workspace_read",
            "git_read",
            "workspace_write",
            "sandbox_execute",
        ),
        "risk_level": "high",
        "recommended_usage": "Use for implementation work that must be verified with tests, lint, build, or controlled shell commands inside an isolated runtime.",
    },
    "network_research": {
        "label": "Network Research",
        "summary": "Allow policy-controlled web and browser research tools when network access is available.",
        "capabilities": ("project_context", "knowledge", "mcp", "web_research", "browser_verify"),
        "risk_level": "medium",
        "recommended_usage": "Use for fact-finding, document collection, browser verification, and web-driven investigation under domain and download policy controls.",
    },
}

CAPABILITY_FAMILY_DETAILS: dict[str, dict[str, Any]] = {
    "builtin": {
        "label": "Builtin",
        "summary": "Low-risk local helper tools such as structured utility or calculation primitives.",
        "risk_level": "low",
    },
    "project_context": {
        "label": "Project Context",
        "summary": "Read uploaded files, conversation context, and mounted project materials without touching the host filesystem.",
        "risk_level": "low",
    },
    "knowledge": {
        "label": "Knowledge",
        "summary": "Retrieve mounted knowledge-base content under tenant and access policy.",
        "risk_level": "low",
    },
    "mcp": {
        "label": "MCP",
        "summary": "Reach external capabilities through governed MCP servers and tool allowlists.",
        "risk_level": "medium",
    },
    "workspace_read": {
        "label": "Workspace Read",
        "summary": "Inspect isolated workspace files, symbols, references, and repository structure.",
        "risk_level": "low",
    },
    "git_read": {
        "label": "Git Read",
        "summary": "Inspect git status, diff, log, show, and branch metadata inside the isolated workspace copy.",
        "risk_level": "low",
    },
    "workspace_write": {
        "label": "Workspace Write",
        "summary": "Edit only the isolated workspace copy; repository writeback remains an explicit later step.",
        "risk_level": "medium",
    },
    "sandbox_execute": {
        "label": "Sandbox Execute",
        "summary": "Run tests, builds, lint, type checks, coverage, or shell commands inside an isolated sandbox runner.",
        "risk_level": "high",
    },
    "web_research": {
        "label": "Web Research",
        "summary": "Search the web, fetch pages, extract content, and download files under network policy.",
        "risk_level": "medium",
    },
    "browser_verify": {
        "label": "Browser Verify",
        "summary": "Drive a browser runtime for verification, screenshots, snapshots, and PDF extraction.",
        "risk_level": "medium",
    },
    "observability": {
        "label": "Observability",
        "summary": "Inspect governed read-only operational data such as DB, Redis, logs, HTTP health, and metrics.",
        "risk_level": "high",
    },
    "workspace_lifecycle": {
        "label": "Workspace Lifecycle",
        "summary": "Inspect and maintain isolated workspace retention, cleanup locks, and writeback hygiene.",
        "risk_level": "medium",
    },
}


@dataclass(frozen=True)
class ExecutionMode:
    name: str
    label: str
    summary: str
    capabilities: tuple[str, ...]
    risk_level: str
    source: str
    recommended_usage: str

    def model_dump(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "summary": self.summary,
            "capabilities": list(self.capabilities),
            "risk_level": self.risk_level,
            "source": self.source,
            "recommended_usage": self.recommended_usage,
            "allowed_modes": list(EXECUTION_MODE_ORDER),
        }


def resolve_tool_capability_family(tool_spec: Mapping[str, Any] | None) -> str | None:
    if not isinstance(tool_spec, Mapping):
        return None

    kind = str(tool_spec.get("kind") or "").strip().lower()
    metadata = tool_spec.get("metadata") if isinstance(tool_spec.get("metadata"), Mapping) else {}
    provider = str(metadata.get("provider") or "").strip().lower()
    legacy_provider = str(metadata.get("legacy_provider") or "").strip().lower()
    capability = str(metadata.get("capability") or "").strip().lower()
    access_level = str(metadata.get("access_level") or "").strip().lower()

    if kind == "builtin" or (not kind and not provider and not capability):
        return "builtin"
    if kind == "knowledge":
        return "knowledge"
    if kind in {"mcp", "mcp-governance"} or provider == "mcp" or capability.startswith("mcp_"):
        return "mcp"
    if (
        kind == "project-context"
        or provider == "project-context"
        or legacy_provider == "engineering"
        or capability == "project_context"
    ):
        return "project_context"
    if capability == "git":
        return "git_read"
    if capability in {"workspace", "code_analysis"}:
        return "workspace_write" if access_level == "write" else "workspace_read"
    if capability == "workspace_lifecycle":
        return "workspace_lifecycle"
    if provider == "sandbox-exec":
        return "sandbox_execute"
    if provider == "web":
        return "browser_verify" if capability == "browser_verify" else "web_research"
    if provider == "observability":
        return "observability"
    return capability or provider or kind or None


def annotate_tool_spec_for_execution_mode(
    tool_spec: Mapping[str, Any],
    execution_mode: ExecutionMode,
) -> dict[str, Any]:
    family = resolve_tool_capability_family(tool_spec)
    allowed = family is None or family == "builtin" or family in set(execution_mode.capabilities)
    metadata = {
        **(tool_spec.get("metadata") or {}),
        "execution_mode": execution_mode.name,
        "execution_mode_policy": execution_mode.model_dump(),
        "execution_mode_capability_family": family,
        "execution_mode_allowed": allowed,
    }
    if not allowed:
        metadata["execution_mode_block_reason"] = (
            f"tool capability family {family} is outside execution mode {execution_mode.name}"
        )
    return {
        **tool_spec,
        "metadata": metadata,
    }


def filter_tool_specs_for_execution_mode(
    tools: list[Mapping[str, Any]],
    execution_mode: ExecutionMode,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for tool in tools:
        annotated = annotate_tool_spec_for_execution_mode(tool, execution_mode)
        if annotated["metadata"].get("execution_mode_allowed"):
            filtered.append(annotated)
    return filtered


def build_execution_mode_surface(
    tools: list[Mapping[str, Any]],
    execution_mode: ExecutionMode,
) -> dict[str, Any]:
    tool_groups: dict[str, list[dict[str, Any]]] = {}
    for tool in tools:
        metadata = tool.get("metadata") if isinstance(tool.get("metadata"), Mapping) else {}
        family = str(metadata.get("execution_mode_capability_family") or resolve_tool_capability_family(tool) or "unknown")
        tool_groups.setdefault(family, []).append(dict(tool))

    capability_keys = []
    seen: set[str] = set()
    for key in ("builtin", *execution_mode.capabilities, *CAPABILITY_FAMILY_DETAILS.keys(), *tool_groups.keys()):
        normalized = str(key or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        capability_keys.append(normalized)

    capability_details: list[dict[str, Any]] = []
    tool_families: list[dict[str, Any]] = []
    for key in capability_keys:
        details = CAPABILITY_FAMILY_DETAILS.get(key, {})
        allowed_modes = [
            mode_name
            for mode_name, mode_details in EXECUTION_MODE_DETAILS.items()
            if key == "builtin" or key in set(mode_details.get("capabilities", ()))
        ]
        enabled = key == "builtin" or key in set(execution_mode.capabilities)
        family_tools = tool_groups.get(key, [])
        allowed_tool_count = sum(
            1
            for tool in family_tools
            if bool(
                (
                    tool.get("metadata")
                    if isinstance(tool.get("metadata"), Mapping)
                    else {}
                ).get("execution_mode_allowed")
            )
        )
        blocked_tool_count = len(family_tools) - allowed_tool_count
        block_reason = (
            ""
            if enabled
            else f"Capability family {key} is outside execution mode {execution_mode.name}"
        )
        capability_details.append(
            {
                "key": key,
                "label": details.get("label") or key.replace("_", " ").title(),
                "summary": details.get("summary") or "",
                "risk_level": details.get("risk_level") or "unknown",
                "enabled": enabled,
                "status": "allowed" if enabled else "blocked",
                "allowed_modes": allowed_modes,
                "block_reason": block_reason,
            }
        )
        if family_tools:
            tool_families.append(
                {
                    "key": key,
                    "label": details.get("label") or key.replace("_", " ").title(),
                    "summary": details.get("summary") or "",
                    "risk_level": details.get("risk_level") or "unknown",
                    "enabled": enabled,
                    "tool_count": len(family_tools),
                    "allowed_tool_count": allowed_tool_count,
                    "blocked_tool_count": blocked_tool_count,
                    "providers": sorted(
                        {
                            str(
                                (
                                    tool.get("metadata")
                                    if isinstance(tool.get("metadata"), Mapping)
                                    else {}
                                ).get("provider")
                                or tool.get("kind")
                                or "unknown"
                            )
                            for tool in family_tools
                        }
                    ),
                    "tool_names_preview": [str(tool.get("name") or "") for tool in family_tools[:8] if str(tool.get("name") or "")],
                    "block_reason": block_reason,
                }
            )

    blocked_tools_preview = [
        {
            "name": str(tool.get("name") or ""),
            "kind": str(tool.get("kind") or ""),
            "capability_family": str(
                (
                    tool.get("metadata")
                    if isinstance(tool.get("metadata"), Mapping)
                    else {}
                ).get("execution_mode_capability_family")
                or resolve_tool_capability_family(tool)
                or "unknown"
            ),
            "block_reason": str(
                (
                    tool.get("metadata")
                    if isinstance(tool.get("metadata"), Mapping)
                    else {}
                ).get("execution_mode_block_reason")
                or ""
            ),
        }
        for tool in tools
        if not bool(
            (
                tool.get("metadata")
                if isinstance(tool.get("metadata"), Mapping)
                else {}
            ).get("execution_mode_allowed")
        )
    ][:12]

    allowed_tool_count = sum(
        1
        for tool in tools
        if bool(
            (
                tool.get("metadata")
                if isinstance(tool.get("metadata"), Mapping)
                else {}
            ).get("execution_mode_allowed")
        )
    )
    blocked_tool_count = len(tools) - allowed_tool_count
    return {
        **execution_mode.model_dump(),
        "catalog_tool_count": len(tools),
        "allowed_tool_count": allowed_tool_count,
        "blocked_tool_count": blocked_tool_count,
        "capability_details": capability_details,
        "tool_families": tool_families,
        "blocked_tools_preview": blocked_tools_preview,
    }


def normalize_execution_mode(
    config: Mapping[str, Any] | None,
    *,
    default: str = "context_only",
) -> ExecutionMode:
    source = "default"
    raw_mode: Any = None
    if isinstance(config, Mapping):
        raw_mode = config.get("execution_mode")
        if raw_mode is None and isinstance(config.get("runtime_policy"), Mapping):
            raw_mode = config["runtime_policy"].get("execution_mode")
        if raw_mode is not None:
            source = "agent_config"

    mode_name = str(raw_mode or default).strip().lower().replace("-", "_")
    if mode_name not in EXECUTION_MODE_DETAILS:
        mode_name = default
        source = "default_invalid"

    details = EXECUTION_MODE_DETAILS[mode_name]
    return ExecutionMode(
        name=mode_name,
        label=str(details["label"]),
        summary=str(details["summary"]),
        capabilities=tuple(details["capabilities"]),
        risk_level=str(details["risk_level"]),
        source=source,
        recommended_usage=str(details.get("recommended_usage") or ""),
    )
