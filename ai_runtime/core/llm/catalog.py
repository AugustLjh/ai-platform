from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any


CATALOG_PATH = Path(__file__).with_name("model_capability_catalog.json")


@lru_cache(maxsize=1)
def load_model_capability_catalog() -> dict[str, Any]:
    with CATALOG_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def infer_model_capabilities(provider: str, model: str) -> dict[str, Any]:
    catalog = load_model_capability_catalog()
    provider_entry = (catalog.get("providers") or {}).get(str(provider or "").strip().lower(), {})
    capabilities = dict(provider_entry.get("defaults") or {})
    normalized_model = str(model or "").strip().lower()
    for entry in provider_entry.get("models") or []:
        pattern = str(entry.get("match") or "").strip()
        if pattern and re.search(pattern, normalized_model):
            capabilities.update(dict(entry.get("capabilities") or {}))
            break
    return capabilities


def model_capability_schema() -> dict[str, Any]:
    return load_model_capability_catalog()
