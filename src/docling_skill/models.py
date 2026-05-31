"""Shared types and models for ingestion outputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, TypedDict

QualityStatus = Literal["good", "salvaged", "failed_for_agent"]
RiskLevel = Literal["low", "medium", "high"]


class ImageSidecar(TypedDict, total=False):
    id: str
    placeholder: str
    self_ref: str | None
    page_no: int | None
    bbox: dict[str, Any] | None
    caption_refs: list[str]
    mime_type: str
    base64: str


class QualityReport(TypedDict, total=False):
    status: QualityStatus
    agent_ready: bool
    reasons: list[str]
    warnings: list[str]
    placeholder_count: int
    non_placeholder_characters: int
    min_required_text_characters: int
    picture_count: int
    content_trust: dict[str, float]
    risk_level: RiskLevel
    gate: str
    limitations: list[str]
    signals: dict[str, Any]


class SpreadsheetMetadata(TypedDict, total=False):
    source_format: str
    normalized_from: str
    sheet_count: int
    table_count: int
    merged_cell_count: int
    has_merged_cells: bool
    has_multi_sheet: bool


class AttemptManifest(TypedDict, total=False):
    contract_version: str
    producer: dict[str, str]
    source_file: str
    input_type: str
    pipeline_family: str
    attempt: str
    status: str
    page_count: int
    image_count: int
    text_characters: int
    document_markdown: str
    images_json: str
    quality: QualityReport
    page_quality: dict[str, QualityReport]
    ocr: dict[str, Any]
    remediated_pages: list[int]
    preferred_agent_artifact: str
    authoritative_artifact: str
    available_artifacts: list[str]
    attempts: list["AttemptManifest"]
    selected_attempt: str
    ocr_remediation_applied: bool
    spreadsheet: SpreadsheetMetadata


class SourceMeta(TypedDict):
    job_id: str | None
    input_type: str
    source_title: str
    source_url: str | None
    source_attachment: str
    author: str | None
    published_at: str | None
    extractor: str
    pipeline_family: str | None
    quality_status: str
    quality_reasons: list[str]
    char_count: int


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
    manifest: AttemptManifest
