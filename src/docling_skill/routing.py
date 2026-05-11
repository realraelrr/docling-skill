"""Input routing helpers for ingestion outputs."""

from __future__ import annotations

from pathlib import Path

from .constants import INPUT_TYPE_BY_SUFFIX


def detect_input_type(input_path: Path) -> str:
    return INPUT_TYPE_BY_SUFFIX.get(input_path.suffix.lower(), "document")
