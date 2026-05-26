"""Splitter factory.

Selects between :class:`CJKAwareTextSplitter` and
:class:`RecursiveCharacterTextSplitter` based on a language profile or
explicit configuration.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional, Union

from langchain_text_splitters import RecursiveCharacterTextSplitter, TextSplitter

from .cjk_aware import CJKAwareTextSplitter, _is_predominantly_cjk


_LANGUAGE_ALIASES: Mapping[str, str] = {
    "cjk": "cjk",
    "chinese": "cjk",
    "zh": "cjk",
    "ja": "cjk",
    "ko": "cjk",
    "japanese": "cjk",
    "korean": "cjk",
    "en": "default",
    "english": "default",
    "default": "default",
    "auto": "auto",
}


def build_splitter(
    profile: Union[Mapping[str, Any], str, None] = None,
    *,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    sample_text: Optional[str] = None,
) -> TextSplitter:
    """Build a :class:`TextSplitter` based on a language profile.

    Parameters
    ----------
    profile
        Either a string language hint (``"cjk"``, ``"zh"``, ``"en"``,
        ``"auto"``, etc.) or a mapping with keys ``language``,
        ``chunk_size``, ``chunk_overlap``.
    chunk_size
        Default chunk size (overridden by profile mapping).
    chunk_overlap
        Default chunk overlap (overridden by profile mapping).
    sample_text
        When *profile* is ``"auto"`` (or not specified), this text is
        inspected to decide whether CJK splitting is appropriate.
    """
    language: str = "auto"

    if isinstance(profile, str):
        language = profile.strip().lower()
    elif isinstance(profile, Mapping):
        language = str(profile.get("language") or profile.get("tokenizer_mode") or "auto").strip().lower()
        chunk_size = int(profile.get("chunk_size") or chunk_size)
        chunk_overlap = int(profile.get("chunk_overlap") or chunk_overlap)

    resolved = _LANGUAGE_ALIASES.get(language, "auto")

    if resolved == "cjk":
        return CJKAwareTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    if resolved == "default":
        return RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    # "auto" — inspect sample_text
    if sample_text and _is_predominantly_cjk(sample_text):
        return CJKAwareTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )


__all__ = ["build_splitter"]
