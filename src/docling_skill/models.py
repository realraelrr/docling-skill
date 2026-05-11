"""Shared type aliases and models for ingestion outputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

ImageSidecar = dict[str, Any]
QualityReport = dict[str, Any]


@dataclass
class PageArtifacts:
    markdown_text: str
    images: list[ImageSidecar]
    quality: QualityReport
    structured_document: dict[str, Any] | None = None


@dataclass
class AttemptArtifacts:
    markdown_text: str
    images: list[ImageSidecar]
    page_outputs: dict[int, PageArtifacts]
    structured_document: dict[str, Any]
    manifest: dict[str, Any]
