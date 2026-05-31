"""Manifest and source metadata helpers for ingestion outputs."""

from __future__ import annotations

import importlib.metadata as package_metadata
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from . import quality as _quality_helpers
from .constants import (
    AUTHORITATIVE_ARTIFACT,
    AVAILABLE_ARTIFACTS,
    CONTRACT_VERSION,
    PREFERRED_AGENT_ARTIFACT,
    PRODUCER_NAME,
    SOURCE_IMAGES_NAME,
    SOURCE_MARKDOWN_NAME,
)
from .models import AttemptManifest, ImageSidecar, PageArtifacts, QualityReport, SourceMeta
from .routing import detect_input_type


def infer_source_title(markdown_text: str, input_path: Path) -> str:
    for raw_line in markdown_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            return re.sub(r"^#+\s*", "", line).strip() or input_path.stem
        return line
    return input_path.stem


def build_source_meta(
    *,
    input_path: Path | str,
    manifest: AttemptManifest,
    markdown_text: str,
    job_id: str | None = None,
    source_title: str | None = None,
    detect_input_type_func=detect_input_type,
    infer_source_title_func=infer_source_title,
) -> SourceMeta:
    normalized_input_path = Path(input_path)
    quality = manifest["quality"]

    return {
        "job_id": job_id,
        "input_type": manifest.get("input_type", detect_input_type_func(normalized_input_path)),
        "source_title": source_title or infer_source_title_func(markdown_text, normalized_input_path),
        "source_url": None,
        "source_attachment": normalized_input_path.name,
        "author": None,
        "published_at": None,
        "extractor": "docling",
        "pipeline_family": manifest.get("pipeline_family"),
        "quality_status": quality["status"],
        "quality_reasons": quality["reasons"],
        "char_count": len(markdown_text),
    }


def _serialize_page_quality(
    page_outputs: dict[int, PageArtifacts],
) -> dict[str, QualityReport]:
    return {
        str(page_no): page_output.quality
        for page_no, page_output in sorted(page_outputs.items())
    }


def _apply_artifact_authority(manifest: AttemptManifest) -> AttemptManifest:
    normalized_manifest = deepcopy(manifest)
    if "quality" in normalized_manifest:
        _quality_helpers._ensure_quality_evidence_fields(normalized_manifest["quality"])
    normalized_manifest["contract_version"] = CONTRACT_VERSION
    normalized_manifest["producer"] = {
        "name": PRODUCER_NAME,
        "version": package_metadata.version(PRODUCER_NAME),
        "docling_version": package_metadata.version("docling"),
        "docling_core_version": package_metadata.version("docling-core"),
    }
    normalized_manifest["preferred_agent_artifact"] = PREFERRED_AGENT_ARTIFACT
    normalized_manifest["authoritative_artifact"] = AUTHORITATIVE_ARTIFACT
    normalized_manifest["available_artifacts"] = list(AVAILABLE_ARTIFACTS)
    return normalized_manifest


def _build_attempt_manifest(
    pdf_path: Path,
    *,
    input_type: str,
    pipeline_family: str,
    attempt_label: str,
    status: str,
    images: list[ImageSidecar],
    markdown_text: str,
    ocr_metadata: dict[str, Any] | None,
    quality: QualityReport,
    page_outputs: dict[int, PageArtifacts],
    page_count: int | None = None,
    remediated_pages: list[int] | None = None,
) -> AttemptManifest:
    manifest = {
        "source_file": str(pdf_path),
        "input_type": input_type,
        "pipeline_family": pipeline_family,
        "attempt": attempt_label,
        "status": status,
        "page_count": page_count if page_count is not None else len(page_outputs),
        "image_count": len(images),
        "text_characters": len(markdown_text),
        "document_markdown": SOURCE_MARKDOWN_NAME,
        "images_json": SOURCE_IMAGES_NAME,
        "quality": quality,
        "page_quality": _serialize_page_quality(page_outputs),
    }
    if ocr_metadata is not None:
        manifest["ocr"] = ocr_metadata
    if remediated_pages:
        manifest["remediated_pages"] = remediated_pages
    return _apply_artifact_authority(manifest)


def _finalize_selected_manifest(manifest: AttemptManifest) -> AttemptManifest:
    finalized = _apply_artifact_authority(manifest)
    quality = _quality_helpers._ensure_quality_evidence_fields(finalized["quality"])

    if finalized.get("attempt") != "primary" and quality.get("agent_ready"):
        quality["status"] = "salvaged"
        if "ocr_remediation_selected" not in quality["reasons"]:
            quality["reasons"] = [*quality["reasons"], "ocr_remediation_selected"]
        _quality_helpers._add_quality_warning(
            quality,
            "ocr_remediation_selected",
            min_risk="medium",
        )

    return finalized
