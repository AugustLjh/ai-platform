from __future__ import annotations

import fnmatch
import hashlib
import os
import subprocess
from datetime import datetime, timezone
from difflib import unified_diff
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from ai_runtime.core.agent_runtime.tools.base import BaseTool, ToolContext, ToolLookupContext, ToolSpec


DEFAULT_WORKSPACE_TOOL_NAMES = (
    "workspace_list_files",
    "workspace_read_file",
    "workspace_search_text",
    "workspace_file_info",
    "workspace_tree",
    "git_status",
    "git_diff",
    "git_show",
    "git_log",
    "git_branch",
)

WORKSPACE_WRITE_TOOL_NAMES = (
    "workspace_apply_patch",
    "workspace_create_file",
    "workspace_write_file",
    "workspace_rename_path",
    "workspace_delete_path",
)

DEFAULT_EXCLUDE_PATTERNS = (
    ".git/**",
    "**/.git/**",
    "__pycache__/**",
    "**/__pycache__/**",
    "node_modules/**",
    "**/node_modules/**",
    ".venv/**",
    "**/.venv/**",
    "venv/**",
    "**/venv/**",
)

DEFAULT_PROTECTED_WRITE_PATTERNS = (
    ".env",
    ".env.*",
    "**/.env",
    "**/.env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "id_rsa",
    "**/id_rsa",
    "poetry.lock",
    "uv.lock",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
)

DELETE_REVIEW_NOTE = "Delete operations are permanent inside the run workspace and must be reviewed before external merge."


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


@dataclass(frozen=True)
class WorkspacePolicy:
    roots: tuple[Path, ...]
    max_read_bytes: int = 512_000
    max_write_bytes: int = 1_000_000
    max_output_chars: int = 40_000
    max_search_file_bytes: int = 1_000_000
    exclude_patterns: tuple[str, ...] = DEFAULT_EXCLUDE_PATTERNS
    protected_write_patterns: tuple[str, ...] = DEFAULT_PROTECTED_WRITE_PATTERNS
    allow_protected_writes: bool = False


def _tool_metadata(
    *,
    capability: str,
    access_level: str,
    side_effect: str = "none",
    risk_level: str = "low",
) -> dict[str, Any]:
    return {
        "provider": "workspace",
        "capability": capability,
        "access_level": access_level,
        "side_effect": side_effect,
        "requires_workspace": True,
        "requires_sandbox": False,
        "risk_level": risk_level,
    }


class WorkspaceTool(BaseTool):
    def __init__(self, policy: WorkspacePolicy) -> None:
        self.policy = policy

    def _resolve_workspace_root(self, context: ToolContext | ToolLookupContext | None = None) -> Path:
        requested = ""
        if context is not None:
            requested = str(getattr(context, "workspace_root", None) or "").strip()
        if not requested and len(self.policy.roots) == 1:
            return self.policy.roots[0]
        if not requested:
            raise ValueError("workspace_root is required for workspace tools")

        candidate = Path(requested).expanduser().resolve(strict=True)
        for root in self.policy.roots:
            if candidate == root or root in candidate.parents:
                return candidate
        raise PermissionError("workspace_root is outside configured workspace roots")

    def _resolve_path(self, context: ToolContext, raw_path: str | None, *, must_exist: bool = True) -> Path:
        workspace_root = self._resolve_workspace_root(context)
        path_text = str(raw_path or ".").strip() or "."
        if os.path.isabs(path_text):
            raise PermissionError("absolute paths are not allowed")

        unresolved = workspace_root.joinpath(path_text)
        try:
            candidate = unresolved.resolve(strict=must_exist)
        except FileNotFoundError:
            raise FileNotFoundError(f"workspace path not found: {path_text}") from None

        if candidate != workspace_root and workspace_root not in candidate.parents:
            raise PermissionError("path escapes the configured workspace root")
        return candidate

    def _resolve_write_path(self, context: ToolContext, raw_path: str | None, *, must_exist: bool) -> Path:
        workspace_root = self._resolve_workspace_root(context)
        path_text = str(raw_path or "").strip()
        if not path_text:
            raise ValueError("path is required")
        if os.path.isabs(path_text):
            raise PermissionError("absolute paths are not allowed")
        if "\x00" in path_text:
            raise ValueError("path must not contain NUL bytes")

        candidate = workspace_root.joinpath(path_text).resolve(strict=must_exist)
        if candidate != workspace_root and workspace_root not in candidate.parents:
            raise PermissionError("path escapes the configured workspace root")
        if candidate == workspace_root:
            raise ValueError("path must refer to a file")
        parent = candidate.parent
        while not parent.exists() and parent != parent.parent:
            parent = parent.parent
        resolved_parent = parent.resolve(strict=True)
        if resolved_parent != workspace_root and workspace_root not in resolved_parent.parents:
            raise PermissionError("path parent escapes the configured workspace root")
        return candidate

    def _relative_path(self, workspace_root: Path, path: Path) -> str:
        if path == workspace_root:
            return "."
        return path.relative_to(workspace_root).as_posix()

    def _excluded(self, relative_path: str) -> bool:
        normalized = relative_path.strip("/")
        return any(fnmatch.fnmatch(normalized, pattern) for pattern in self.policy.exclude_patterns)

    def _protected_for_write(self, relative_path: str) -> bool:
        if self.policy.allow_protected_writes:
            return False
        normalized = relative_path.strip("/")
        return any(fnmatch.fnmatch(normalized, pattern) for pattern in self.policy.protected_write_patterns)

    def _validate_write_target(self, workspace_root: Path, path: Path, *, allow_existing: bool) -> str:
        rel = self._relative_path(workspace_root, path)
        if self._excluded(rel):
            raise PermissionError("path is excluded from workspace writes")
        if self._protected_for_write(rel):
            raise PermissionError("path is protected from workspace writes")
        if path.exists():
            if not path.is_file():
                raise ValueError("path must be a file")
            if not allow_existing:
                raise FileExistsError(f"workspace path already exists: {rel}")
        return rel

    def _validate_existing_write_target(self, workspace_root: Path, path: Path) -> str:
        rel = self._relative_path(workspace_root, path)
        if self._excluded(rel):
            raise PermissionError("path is excluded from workspace writes")
        if self._protected_for_write(rel):
            raise PermissionError("path is protected from workspace writes")
        if not path.exists():
            raise FileNotFoundError(f"workspace path not found: {rel}")
        return rel

    def _truncate_text(self, text: str, max_chars: int | None = None) -> tuple[str, bool]:
        limit = max_chars or self.policy.max_output_chars
        if len(text) <= limit:
            return text, False
        return text[:limit], True

    def _read_text(self, path: Path, *, max_chars: int) -> tuple[str, bool, int]:
        stat = path.stat()
        byte_limit = min(self.policy.max_read_bytes, max(max_chars * 4, 1024))
        with path.open("rb") as handle:
            data = handle.read(byte_limit + 1)
        byte_truncated = len(data) > byte_limit or stat.st_size > byte_limit
        if byte_truncated:
            data = data[:byte_limit]
        text = data.decode("utf-8", errors="replace")
        text, char_truncated = self._truncate_text(text, max_chars)
        return text, byte_truncated or char_truncated or stat.st_size > len(data), stat.st_size

    def _file_digest(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def _text_digest(self, content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _coerce_content(self, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("content must be a string")
        size = len(value.encode("utf-8"))
        if size > self.policy.max_write_bytes:
            raise ValueError("content exceeds workspace write size limit")
        return value

    def _unified_file_diff(self, *, relative_path: str, before: str, after: str, max_chars: int) -> tuple[str, bool]:
        diff_text = "".join(
            unified_diff(
                before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile=f"a/{relative_path}",
                tofile=f"b/{relative_path}",
            )
        )
        return self._truncate_text(diff_text, max_chars)

    def _patch_artifact(
        self,
        *,
        operation: str,
        changed_files: list[dict[str, Any]],
        diff: str,
        dry_run: bool,
        status: str,
        truncated: bool,
        review_notes: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "artifact_type": "code_patch",
            "name": "Workspace Patch",
            "payload": {
                "operation": operation,
                "status": status,
                "dry_run": dry_run,
                "files": changed_files,
                "diff": diff,
                "truncated": truncated,
                "review_notes": review_notes or [],
                "merge_policy": "manual_review_required",
            },
            "metadata": {
                "source": "workspace",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
        }

    def _run_git(self, context: ToolContext, args: list[str], *, max_chars: int) -> dict[str, Any]:
        workspace_root = self._resolve_workspace_root(context)
        command = ["git", "-C", str(workspace_root), *args]
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        stdout, stdout_truncated = self._truncate_text(completed.stdout or "", max_chars)
        stderr, stderr_truncated = self._truncate_text(completed.stderr or "", max_chars)
        return {
            "command": ["git", *args],
            "exit_code": completed.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "truncated": stdout_truncated or stderr_truncated,
        }


class WorkspaceListFilesTool(WorkspaceTool):
    spec = ToolSpec(
        name="workspace_list_files",
        description="List files and directories inside the configured workspace root. Path traversal and symlink escapes are rejected.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "recursive": {"type": "boolean"},
                "max_entries": {"type": "integer", "minimum": 1, "maximum": 1000},
            },
        },
        kind="workspace",
        metadata=_tool_metadata(capability="workspace", access_level="read"),
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        workspace_root = self._resolve_workspace_root(context)
        base_path = self._resolve_path(context, arguments.get("path"))
        if not base_path.is_dir():
            raise ValueError("path must be a directory")

        recursive = bool(arguments.get("recursive"))
        max_entries = _clamp_int(arguments.get("max_entries"), default=100, minimum=1, maximum=1000)
        iterator = base_path.rglob("*") if recursive else base_path.iterdir()
        entries: list[dict[str, Any]] = []
        truncated = False
        for item in sorted(iterator, key=lambda value: value.as_posix()):
            rel = self._relative_path(workspace_root, item)
            if self._excluded(rel):
                continue
            try:
                resolved = item.resolve(strict=True)
            except FileNotFoundError:
                continue
            if resolved != workspace_root and workspace_root not in resolved.parents:
                continue
            stat = item.stat()
            entries.append(
                {
                    "path": rel,
                    "type": "directory" if item.is_dir() else "file",
                    "size_bytes": stat.st_size if item.is_file() else None,
                }
            )
            if len(entries) >= max_entries:
                truncated = True
                break

        return {
            "workspace_root": str(workspace_root),
            "path": self._relative_path(workspace_root, base_path),
            "recursive": recursive,
            "entries": entries,
            "truncated": truncated,
        }


class WorkspaceReadFileTool(WorkspaceTool):
    spec = ToolSpec(
        name="workspace_read_file",
        description="Read a UTF-8 text file from the configured workspace root with size and output truncation.",
        input_schema={
            "type": "object",
            "required": ["path"],
            "properties": {
                "path": {"type": "string"},
                "max_chars": {"type": "integer", "minimum": 100, "maximum": 50000},
            },
        },
        kind="workspace",
        metadata=_tool_metadata(capability="workspace", access_level="read"),
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        workspace_root = self._resolve_workspace_root(context)
        path = self._resolve_path(context, str(arguments.get("path") or ""))
        if not path.is_file():
            raise ValueError("path must be a file")
        rel = self._relative_path(workspace_root, path)
        if self._excluded(rel):
            raise PermissionError("path is excluded from workspace reads")
        max_chars = _clamp_int(arguments.get("max_chars"), default=8000, minimum=100, maximum=50000)
        content, truncated, size_bytes = self._read_text(path, max_chars=max_chars)
        return {
            "path": rel,
            "size_bytes": size_bytes,
            "content": content,
            "truncated": truncated,
        }


class WorkspaceSearchTextTool(WorkspaceTool):
    spec = ToolSpec(
        name="workspace_search_text",
        description="Search text files inside the configured workspace root and return bounded line matches.",
        input_schema={
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "path": {"type": "string"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 200},
                "max_line_chars": {"type": "integer", "minimum": 80, "maximum": 1000},
            },
        },
        kind="workspace",
        metadata=_tool_metadata(capability="workspace", access_level="read"),
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments.get("query") or "").strip()
        if not query:
            raise ValueError("query is required")
        workspace_root = self._resolve_workspace_root(context)
        base_path = self._resolve_path(context, arguments.get("path"))
        max_results = _clamp_int(arguments.get("max_results"), default=50, minimum=1, maximum=200)
        max_line_chars = _clamp_int(arguments.get("max_line_chars"), default=240, minimum=80, maximum=1000)
        files = [base_path] if base_path.is_file() else base_path.rglob("*")
        matches: list[dict[str, Any]] = []
        truncated = False
        needle = query.lower()

        for path in sorted(files, key=lambda value: value.as_posix()):
            if not path.is_file():
                continue
            rel = self._relative_path(workspace_root, path)
            if self._excluded(rel) or path.stat().st_size > self.policy.max_search_file_bytes:
                continue
            try:
                resolved = path.resolve(strict=True)
            except FileNotFoundError:
                continue
            if resolved != workspace_root and workspace_root not in resolved.parents:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for line_number, line in enumerate(text.splitlines(), start=1):
                if needle not in line.lower():
                    continue
                preview, line_truncated = self._truncate_text(line.strip(), max_line_chars)
                matches.append(
                    {
                        "path": rel,
                        "line": line_number,
                        "preview": preview,
                        "line_truncated": line_truncated,
                    }
                )
                if len(matches) >= max_results:
                    truncated = True
                    break
            if truncated:
                break

        return {
            "query": query,
            "path": self._relative_path(workspace_root, base_path),
            "matches": matches,
            "total": len(matches),
            "truncated": truncated,
        }


class WorkspaceFileInfoTool(WorkspaceTool):
    spec = ToolSpec(
        name="workspace_file_info",
        description="Return bounded metadata for a file or directory inside the configured workspace root.",
        input_schema={
            "type": "object",
            "required": ["path"],
            "properties": {
                "path": {"type": "string"},
                "include_hash": {"type": "boolean"},
            },
        },
        kind="workspace",
        metadata=_tool_metadata(capability="workspace", access_level="read"),
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        workspace_root = self._resolve_workspace_root(context)
        path = self._resolve_path(context, str(arguments.get("path") or ""))
        rel = self._relative_path(workspace_root, path)
        if self._excluded(rel):
            raise PermissionError("path is excluded from workspace reads")

        stat = path.stat()
        result: dict[str, Any] = {
            "path": rel,
            "type": "directory" if path.is_dir() else "file",
            "size_bytes": stat.st_size if path.is_file() else None,
            "modified_at": int(stat.st_mtime),
            "is_symlink": path.is_symlink(),
        }
        if path.is_file():
            result["extension"] = path.suffix
            result["readable_text"] = stat.st_size <= self.policy.max_read_bytes
            if bool(arguments.get("include_hash")) and stat.st_size <= self.policy.max_read_bytes:
                result["sha256"] = self._file_digest(path)
        if path.is_dir():
            visible_children = 0
            for child in path.iterdir():
                child_rel = self._relative_path(workspace_root, child)
                if not self._excluded(child_rel):
                    visible_children += 1
            result["visible_child_count"] = visible_children
        return result


class WorkspaceTreeTool(WorkspaceTool):
    spec = ToolSpec(
        name="workspace_tree",
        description="Return a bounded directory tree inside the configured workspace root.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "max_depth": {"type": "integer", "minimum": 1, "maximum": 8},
                "max_entries": {"type": "integer", "minimum": 1, "maximum": 1000},
            },
        },
        kind="workspace",
        metadata=_tool_metadata(capability="workspace", access_level="read"),
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        workspace_root = self._resolve_workspace_root(context)
        base_path = self._resolve_path(context, arguments.get("path"))
        if not base_path.is_dir():
            raise ValueError("path must be a directory")

        max_depth = _clamp_int(arguments.get("max_depth"), default=3, minimum=1, maximum=8)
        max_entries = _clamp_int(arguments.get("max_entries"), default=200, minimum=1, maximum=1000)
        entries: list[dict[str, Any]] = []
        truncated = False

        def walk(directory: Path, depth: int) -> None:
            nonlocal truncated
            if truncated or depth > max_depth:
                return
            try:
                children = sorted(directory.iterdir(), key=lambda value: (not value.is_dir(), value.name.lower()))
            except OSError:
                return
            for child in children:
                if truncated:
                    break
                rel = self._relative_path(workspace_root, child)
                if self._excluded(rel):
                    continue
                try:
                    resolved = child.resolve(strict=True)
                except FileNotFoundError:
                    continue
                if resolved != workspace_root and workspace_root not in resolved.parents:
                    continue
                stat = child.stat()
                entries.append(
                    {
                        "path": rel,
                        "depth": depth,
                        "type": "directory" if child.is_dir() else "file",
                        "size_bytes": stat.st_size if child.is_file() else None,
                    }
                )
                if len(entries) >= max_entries:
                    truncated = True
                    break
                if child.is_dir():
                    walk(child, depth + 1)

        walk(base_path, 1)
        return {
            "workspace_root": str(workspace_root),
            "path": self._relative_path(workspace_root, base_path),
            "max_depth": max_depth,
            "entries": entries,
            "truncated": truncated,
        }


class WorkspaceApplyPatchTool(WorkspaceTool):
    spec = ToolSpec(
        name="workspace_apply_patch",
        description="Apply a full-file text replacement inside the configured workspace and return a reviewable patch artifact.",
        input_schema={
            "type": "object",
            "required": ["path", "content"],
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "expected_sha256": {"type": "string"},
                "dry_run": {"type": "boolean"},
                "max_diff_chars": {"type": "integer", "minimum": 100, "maximum": 100000},
            },
        },
        kind="workspace",
        metadata=_tool_metadata(
            capability="workspace",
            access_level="write",
            side_effect="workspace_write",
            risk_level="medium",
        ),
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        workspace_root = self._resolve_workspace_root(context)
        path = self._resolve_write_path(context, str(arguments.get("path") or ""), must_exist=True)
        rel = self._validate_write_target(workspace_root, path, allow_existing=True)
        before = path.read_text(encoding="utf-8", errors="replace")
        before_sha256 = self._file_digest(path)
        expected_sha256 = str(arguments.get("expected_sha256") or "").strip()
        if expected_sha256 and expected_sha256 != before_sha256:
            raise ValueError("expected_sha256 does not match current file content")

        after = self._coerce_content(arguments.get("content"))
        after_sha256 = self._text_digest(after)
        max_diff_chars = _clamp_int(arguments.get("max_diff_chars"), default=40000, minimum=100, maximum=100000)
        diff, diff_truncated = self._unified_file_diff(
            relative_path=rel,
            before=before,
            after=after,
            max_chars=max_diff_chars,
        )
        dry_run = bool(arguments.get("dry_run"))
        changed = before != after
        if changed and not dry_run:
            path.write_text(after, encoding="utf-8")

        status = "dry_run" if dry_run else "applied"
        changed_files = [
            {
                "path": rel,
                "operation": "modify",
                "before_sha256": before_sha256,
                "after_sha256": after_sha256,
                "size_bytes": len(after.encode("utf-8")),
                "changed": changed,
            }
        ]
        artifact = self._patch_artifact(
            operation="modify",
            changed_files=changed_files,
            diff=diff,
            dry_run=dry_run,
            status=status,
            truncated=diff_truncated,
        )
        return {
            "status": status,
            "path": rel,
            "operation": "modify",
            "dry_run": dry_run,
            "changed": changed,
            "before_sha256": before_sha256,
            "after_sha256": after_sha256,
            "diff": diff,
            "truncated": diff_truncated,
            "artifacts": [artifact],
        }


class WorkspaceCreateFileTool(WorkspaceTool):
    spec = ToolSpec(
        name="workspace_create_file",
        description="Create a new UTF-8 text file inside the configured workspace and return a reviewable patch artifact.",
        input_schema={
            "type": "object",
            "required": ["path", "content"],
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "dry_run": {"type": "boolean"},
                "max_diff_chars": {"type": "integer", "minimum": 100, "maximum": 100000},
            },
        },
        kind="workspace",
        metadata=_tool_metadata(
            capability="workspace",
            access_level="write",
            side_effect="workspace_write",
            risk_level="medium",
        ),
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        workspace_root = self._resolve_workspace_root(context)
        path = self._resolve_write_path(context, str(arguments.get("path") or ""), must_exist=False)
        rel = self._validate_write_target(workspace_root, path, allow_existing=False)
        content = self._coerce_content(arguments.get("content"))
        after_sha256 = self._text_digest(content)
        max_diff_chars = _clamp_int(arguments.get("max_diff_chars"), default=40000, minimum=100, maximum=100000)
        diff, diff_truncated = self._unified_file_diff(relative_path=rel, before="", after=content, max_chars=max_diff_chars)
        dry_run = bool(arguments.get("dry_run"))
        if not dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

        status = "dry_run" if dry_run else "applied"
        changed_files = [
            {
                "path": rel,
                "operation": "create",
                "before_sha256": None,
                "after_sha256": after_sha256,
                "size_bytes": len(content.encode("utf-8")),
                "changed": True,
            }
        ]
        artifact = self._patch_artifact(
            operation="create",
            changed_files=changed_files,
            diff=diff,
            dry_run=dry_run,
            status=status,
            truncated=diff_truncated,
        )
        return {
            "status": status,
            "path": rel,
            "operation": "create",
            "dry_run": dry_run,
            "changed": True,
            "before_sha256": None,
            "after_sha256": after_sha256,
            "diff": diff,
            "truncated": diff_truncated,
            "artifacts": [artifact],
        }


class WorkspaceWriteFileTool(WorkspaceTool):
    spec = ToolSpec(
        name="workspace_write_file",
        description="Write a UTF-8 text file inside the configured workspace, optionally creating it, and return a reviewable patch artifact.",
        input_schema={
            "type": "object",
            "required": ["path", "content"],
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "expected_sha256": {"type": "string"},
                "create": {"type": "boolean"},
                "dry_run": {"type": "boolean"},
                "max_diff_chars": {"type": "integer", "minimum": 100, "maximum": 100000},
            },
        },
        kind="workspace",
        metadata=_tool_metadata(
            capability="workspace",
            access_level="write",
            side_effect="workspace_write",
            risk_level="medium",
        ),
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        create = bool(arguments.get("create"))
        path = self._resolve_write_path(context, str(arguments.get("path") or ""), must_exist=not create)
        if path.exists():
            tool = WorkspaceApplyPatchTool(self.policy)
            return await tool.execute(context, arguments)
        if not create:
            raise FileNotFoundError(f"workspace path not found: {arguments.get('path')}")
        tool = WorkspaceCreateFileTool(self.policy)
        return await tool.execute(context, arguments)


class WorkspaceRenamePathTool(WorkspaceTool):
    spec = ToolSpec(
        name="workspace_rename_path",
        description="Rename or move a file inside the configured workspace and return a reviewable patch artifact.",
        input_schema={
            "type": "object",
            "required": ["source_path", "target_path"],
            "properties": {
                "source_path": {"type": "string"},
                "target_path": {"type": "string"},
                "expected_sha256": {"type": "string"},
                "dry_run": {"type": "boolean"},
                "max_diff_chars": {"type": "integer", "minimum": 100, "maximum": 100000},
            },
        },
        kind="workspace",
        metadata=_tool_metadata(
            capability="workspace",
            access_level="write",
            side_effect="workspace_write",
            risk_level="medium",
        ),
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        workspace_root = self._resolve_workspace_root(context)
        source = self._resolve_write_path(context, str(arguments.get("source_path") or ""), must_exist=True)
        target = self._resolve_write_path(context, str(arguments.get("target_path") or ""), must_exist=False)
        source_rel = self._validate_existing_write_target(workspace_root, source)
        target_rel = self._validate_write_target(workspace_root, target, allow_existing=False)
        if not source.is_file():
            raise ValueError("source_path must refer to a file")
        if target.exists():
            raise FileExistsError(f"workspace path already exists: {target_rel}")

        before = source.read_text(encoding="utf-8", errors="replace")
        before_sha256 = self._file_digest(source)
        expected_sha256 = str(arguments.get("expected_sha256") or "").strip()
        if expected_sha256 and expected_sha256 != before_sha256:
            raise ValueError("expected_sha256 does not match current file content")

        max_diff_chars = _clamp_int(arguments.get("max_diff_chars"), default=40000, minimum=100, maximum=100000)
        remove_diff, remove_truncated = self._unified_file_diff(relative_path=source_rel, before=before, after="", max_chars=max_diff_chars)
        remaining_chars = max(100, max_diff_chars - len(remove_diff))
        add_diff, add_truncated = self._unified_file_diff(relative_path=target_rel, before="", after=before, max_chars=remaining_chars)
        diff, combined_truncated = self._truncate_text(remove_diff + add_diff, max_diff_chars)
        diff_truncated = remove_truncated or add_truncated or combined_truncated

        dry_run = bool(arguments.get("dry_run"))
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            source.rename(target)

        status = "dry_run" if dry_run else "applied"
        changed_files = [
            {
                "path": source_rel,
                "operation": "delete",
                "before_sha256": before_sha256,
                "after_sha256": None,
                "size_bytes": 0,
                "changed": True,
            },
            {
                "path": target_rel,
                "operation": "create",
                "before_sha256": None,
                "after_sha256": before_sha256,
                "size_bytes": len(before.encode("utf-8")),
                "changed": True,
            },
        ]
        artifact = self._patch_artifact(
            operation="rename",
            changed_files=changed_files,
            diff=diff,
            dry_run=dry_run,
            status=status,
            truncated=diff_truncated,
            review_notes=[f"Rename {source_rel} to {target_rel}."],
        )
        return {
            "status": status,
            "path": target_rel,
            "source_path": source_rel,
            "target_path": target_rel,
            "operation": "rename",
            "dry_run": dry_run,
            "changed": True,
            "before_sha256": before_sha256,
            "after_sha256": before_sha256,
            "diff": diff,
            "truncated": diff_truncated,
            "artifacts": [artifact],
        }


class WorkspaceDeletePathTool(WorkspaceTool):
    spec = ToolSpec(
        name="workspace_delete_path",
        description="Delete a file inside the configured workspace and return a reviewable patch artifact. Directory deletion is not supported.",
        input_schema={
            "type": "object",
            "required": ["path"],
            "properties": {
                "path": {"type": "string"},
                "expected_sha256": {"type": "string"},
                "dry_run": {"type": "boolean"},
                "max_diff_chars": {"type": "integer", "minimum": 100, "maximum": 100000},
            },
        },
        kind="workspace",
        metadata=_tool_metadata(
            capability="workspace",
            access_level="write",
            side_effect="workspace_write",
            risk_level="high",
        ),
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        workspace_root = self._resolve_workspace_root(context)
        path = self._resolve_write_path(context, str(arguments.get("path") or ""), must_exist=True)
        rel = self._validate_existing_write_target(workspace_root, path)
        if not path.is_file():
            raise ValueError("path must be a file")

        before = path.read_text(encoding="utf-8", errors="replace")
        before_sha256 = self._file_digest(path)
        expected_sha256 = str(arguments.get("expected_sha256") or "").strip()
        if expected_sha256 and expected_sha256 != before_sha256:
            raise ValueError("expected_sha256 does not match current file content")

        max_diff_chars = _clamp_int(arguments.get("max_diff_chars"), default=40000, minimum=100, maximum=100000)
        diff, diff_truncated = self._unified_file_diff(relative_path=rel, before=before, after="", max_chars=max_diff_chars)
        dry_run = bool(arguments.get("dry_run"))
        if not dry_run:
            path.unlink()

        status = "dry_run" if dry_run else "applied"
        changed_files = [
            {
                "path": rel,
                "operation": "delete",
                "before_sha256": before_sha256,
                "after_sha256": None,
                "size_bytes": 0,
                "changed": True,
            }
        ]
        artifact = self._patch_artifact(
            operation="delete",
            changed_files=changed_files,
            diff=diff,
            dry_run=dry_run,
            status=status,
            truncated=diff_truncated,
            review_notes=[DELETE_REVIEW_NOTE],
        )
        return {
            "status": status,
            "path": rel,
            "operation": "delete",
            "dry_run": dry_run,
            "changed": True,
            "before_sha256": before_sha256,
            "after_sha256": None,
            "diff": diff,
            "truncated": diff_truncated,
            "artifacts": [artifact],
        }


class GitStatusTool(WorkspaceTool):
    spec = ToolSpec(
        name="git_status",
        description="Return porcelain git status for the configured workspace root.",
        input_schema={"type": "object", "properties": {"max_chars": {"type": "integer", "minimum": 100, "maximum": 50000}}},
        kind="workspace",
        metadata=_tool_metadata(capability="git", access_level="read"),
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        max_chars = _clamp_int(arguments.get("max_chars"), default=12000, minimum=100, maximum=50000)
        return self._run_git(context, ["status", "--short"], max_chars=max_chars)


class GitDiffTool(WorkspaceTool):
    spec = ToolSpec(
        name="git_diff",
        description="Return git diff output for the configured workspace root. This is read-only.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "staged": {"type": "boolean"},
                "max_chars": {"type": "integer", "minimum": 100, "maximum": 80000},
            },
        },
        kind="workspace",
        metadata=_tool_metadata(capability="git", access_level="read"),
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        max_chars = _clamp_int(arguments.get("max_chars"), default=20000, minimum=100, maximum=80000)
        args = ["diff"]
        if bool(arguments.get("staged")):
            args.append("--cached")
        raw_path = str(arguments.get("path") or "").strip()
        if raw_path:
            self._resolve_path(context, raw_path)
            args.extend(["--", raw_path])
        return self._run_git(context, args, max_chars=max_chars)


class GitShowTool(WorkspaceTool):
    spec = ToolSpec(
        name="git_show",
        description="Return a bounded git show result for a revision or object in the configured workspace root.",
        input_schema={
            "type": "object",
            "properties": {
                "rev": {"type": "string"},
                "max_chars": {"type": "integer", "minimum": 100, "maximum": 80000},
            },
        },
        kind="workspace",
        metadata=_tool_metadata(capability="git", access_level="read"),
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        rev = str(arguments.get("rev") or "HEAD").strip() or "HEAD"
        max_chars = _clamp_int(arguments.get("max_chars"), default=20000, minimum=100, maximum=80000)
        return self._run_git(context, ["show", "--stat", "--patch", rev], max_chars=max_chars)


class GitLogTool(WorkspaceTool):
    spec = ToolSpec(
        name="git_log",
        description="Return recent git commits for the configured workspace root.",
        input_schema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                "max_chars": {"type": "integer", "minimum": 100, "maximum": 50000},
            },
        },
        kind="workspace",
        metadata=_tool_metadata(capability="git", access_level="read"),
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        limit = _clamp_int(arguments.get("limit"), default=10, minimum=1, maximum=50)
        max_chars = _clamp_int(arguments.get("max_chars"), default=16000, minimum=100, maximum=50000)
        return self._run_git(context, ["log", f"--max-count={limit}", "--date=iso", "--pretty=format:%h %ad %an %s"], max_chars=max_chars)


class GitBranchTool(WorkspaceTool):
    spec = ToolSpec(
        name="git_branch",
        description="Return local branch information for the configured workspace root.",
        input_schema={"type": "object", "properties": {"max_chars": {"type": "integer", "minimum": 100, "maximum": 50000}}},
        kind="workspace",
        metadata=_tool_metadata(capability="git", access_level="read"),
    )

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        max_chars = _clamp_int(arguments.get("max_chars"), default=12000, minimum=100, maximum=50000)
        return self._run_git(context, ["branch", "--list", "--verbose", "--no-abbrev"], max_chars=max_chars)


WORKSPACE_TOOL_TYPES = {
    "workspace_list_files": WorkspaceListFilesTool,
    "workspace_read_file": WorkspaceReadFileTool,
    "workspace_search_text": WorkspaceSearchTextTool,
    "workspace_file_info": WorkspaceFileInfoTool,
    "workspace_tree": WorkspaceTreeTool,
    "workspace_apply_patch": WorkspaceApplyPatchTool,
    "workspace_create_file": WorkspaceCreateFileTool,
    "workspace_write_file": WorkspaceWriteFileTool,
    "workspace_rename_path": WorkspaceRenamePathTool,
    "workspace_delete_path": WorkspaceDeletePathTool,
    "git_status": GitStatusTool,
    "git_diff": GitDiffTool,
    "git_show": GitShowTool,
    "git_log": GitLogTool,
    "git_branch": GitBranchTool,
}


class WorkspaceToolProvider:
    def __init__(self, *, enabled_tool_names: Sequence[str], roots: Sequence[str | Path]) -> None:
        resolved_roots = []
        for root in roots:
            root_text = str(root or "").strip()
            if not root_text:
                continue
            path = Path(root_text).expanduser()
            if path.exists():
                resolved_roots.append(path.resolve(strict=True))
        self.policy = WorkspacePolicy(roots=tuple(dict.fromkeys(resolved_roots)))
        self.enabled_tool_names = [name for name in enabled_tool_names if name in WORKSPACE_TOOL_TYPES]

    @classmethod
    def from_env(cls) -> "WorkspaceToolProvider":
        roots = _parse_csv(os.getenv("AGENT_WORKSPACE_ROOTS"), ())
        enabled_tool_names = _parse_csv(os.getenv("AGENT_WORKSPACE_TOOLS"), DEFAULT_WORKSPACE_TOOL_NAMES)
        return cls(enabled_tool_names=enabled_tool_names, roots=roots)

    def _build_tool(self, name: str, context: ToolLookupContext | None = None) -> BaseTool | None:
        if not self.policy.roots:
            return None
        tool_type = WORKSPACE_TOOL_TYPES.get(name)
        if tool_type is None or name not in self.enabled_tool_names:
            return None
        tool = tool_type(self.policy)
        if context is not None:
            tool._resolve_workspace_root(context)
        return tool

    async def get(self, name: str, context: ToolLookupContext | None = None) -> BaseTool | None:
        return self._build_tool(name, context=context)

    async def get_spec(self, name: str, context: ToolLookupContext | None = None) -> dict | None:
        tool = self._build_tool(name, context=context)
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
        items = []
        for name in self.enabled_tool_names:
            try:
                spec = await self.get_spec(name, context=context)
            except (PermissionError, ValueError, FileNotFoundError):
                continue
            if spec is not None:
                items.append(spec)
        return items
