from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from core.agent_runtime.skills.contract import apply_skill_contract
from core.agent_runtime.skills.models import SkillDefinition


def _parse_json(value: Any, fallback: Dict[str, Any] | list[Any]):
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


def _parse_skill_manifest(raw: str) -> Dict[str, str]:
    parsed: Dict[str, str] = {}
    for line in raw.splitlines():
        parts = line.split(":", 1)
        if len(parts) != 2:
            continue
        key = parts[0].strip()
        value = parts[1].strip().strip("\"'")
        if key:
            parsed[key] = value
    return parsed


def load_skill_directory(path: str | Path) -> SkillDefinition:
    root = Path(path)
    manifest = _parse_skill_manifest((root / "skill.yaml").read_text(encoding="utf-8")) if (root / "skill.yaml").exists() else {}
    system_prompt = (root / "system_prompt.md").read_text(encoding="utf-8") if (root / "system_prompt.md").exists() else ""
    output_schema = _parse_json((root / "output_schema.json").read_text(encoding="utf-8"), {})
    tool_allowlist = _parse_json((root / "tool_allowlist.json").read_text(encoding="utf-8"), []) if (root / "tool_allowlist.json").exists() else []
    metadata = _parse_json((root / "metadata.json").read_text(encoding="utf-8"), {}) if (root / "metadata.json").exists() else {}

    slug = manifest.get("slug") or root.name
    skill = SkillDefinition(
        slug=slug,
        name=manifest.get("name") or slug,
        version=manifest.get("version") or "1",
        description=manifest.get("description") or "",
        root_path=str(root),
        system_prompt=system_prompt,
        output_schema=output_schema if isinstance(output_schema, dict) else {},
        tool_allowlist=[str(item) for item in tool_allowlist] if isinstance(tool_allowlist, list) else [],
        metadata=metadata if isinstance(metadata, dict) else {},
    )
    return apply_skill_contract(skill)


def load_skill_row(row: Any) -> SkillDefinition:
    data = dict(row) if hasattr(row, "keys") else dict(row or {})
    skill = SkillDefinition(
        id=str(data.get("id")) if data.get("id") is not None else None,
        slug=str(data.get("slug") or ""),
        name=str(data.get("name") or data.get("slug") or ""),
        version=str(data.get("version") or "1"),
        description=str(data.get("description") or ""),
        root_path=str(data.get("root_path") or ""),
        system_prompt=str(data.get("system_prompt") or ""),
        output_schema=_parse_json(data.get("output_schema"), {}),
        tool_allowlist=[str(item) for item in _parse_json(data.get("tool_allowlist"), []) if str(item).strip()],
        metadata=_parse_json(data.get("metadata"), {}),
        contract=_parse_json(data.get("contract"), {}),
    )

    root_path = Path(skill.root_path) if skill.root_path else None
    if root_path and root_path.exists():
        disk_skill = load_skill_directory(root_path)
        skill = disk_skill.model_copy(
            update={
                "id": skill.id,
            }
        )
    return apply_skill_contract(skill)
