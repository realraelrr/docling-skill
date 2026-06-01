"""Manifest and source metadata helpers for ingestion outputs."""

from __future__ import annotations

import importlib.metadata as package_metadata
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from . import quality as _quality_helpers
from .constants import (
    CONTRACT_VERSION,
    PRODUCER_NAME,
    PRODUCER_VERSION,
    SOURCE_EVIDENCE_NAME,
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
    normalized_manifest["producer"] = _producer_metadata()
    return normalized_manifest


def _producer_metadata() -> dict[str, str]:
    return {
        "name": PRODUCER_NAME,
        "version": PRODUCER_VERSION,
        "docling_version": package_metadata.version("docling"),
        "docling_core_version": package_metadata.version("docling-core"),
    }


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


def _read_order_for_quality(quality: QualityReport) -> list[str]:
    if not quality.get("agent_ready", False):
        return [SOURCE_EVIDENCE_NAME]
    if quality.get("risk_level") == "low" and not quality.get("warnings", []):
        return [SOURCE_MARKDOWN_NAME]
    return [SOURCE_MARKDOWN_NAME, SOURCE_EVIDENCE_NAME]


def _source_summary(
    *,
    input_path: Path,
    selected_manifest: AttemptManifest,
    markdown_text: str,
) -> dict[str, Any]:
    return {
        "file": str(input_path),
        "attachment": input_path.name,
        "title": infer_source_title(markdown_text, input_path),
        "input_type": selected_manifest.get("input_type", detect_input_type(input_path)),
        "pipeline_family": selected_manifest.get("pipeline_family"),
    }


def _build_agent_manifest(
    *,
    input_path: Path,
    selected_manifest: AttemptManifest,
    markdown_text: str,
) -> dict[str, Any]:
    quality = selected_manifest["quality"]
    _quality_helpers._ensure_quality_evidence_fields(quality)
    page_count = selected_manifest.get("page_count", 0)

    return {
        "contract_version": CONTRACT_VERSION,
        "producer": _producer_metadata(),
        "decision": {
            "status": quality["status"],
            "risk_level": quality["risk_level"],
            "agent_ready": quality["agent_ready"],
            "read_order": _read_order_for_quality(quality),
        },
        "source": _source_summary(
            input_path=input_path,
            selected_manifest=selected_manifest,
            markdown_text=markdown_text,
        ),
        "artifacts": {
            "content": SOURCE_MARKDOWN_NAME,
            "evidence": SOURCE_EVIDENCE_NAME,
        },
        "warnings": list(quality.get("warnings", [])),
        "reasons": list(quality.get("reasons", [])),
        "counts": {
            "characters": len(markdown_text),
            "images": selected_manifest.get("image_count", 0),
            "pages": page_count,
        },
    }


def _pdf_audit_evidence(*, input_type: str, pdf_audit: bool) -> dict[str, Any]:
    eligible = input_type in {"docx", "html", "pptx"}
    if not eligible:
        return {
            "enabled": False,
            "status": "not_applicable",
        }
    if not pdf_audit:
        return {
            "enabled": False,
            "status": "disabled",
        }
    return {
        "enabled": True,
        "status": "unavailable",
        "reason": "PDF audit renderer is not implemented in this v2 adapter.",
    }


def _build_evidence(
    *,
    input_path: Path,
    selected_manifest: AttemptManifest,
    attempts: list[AttemptManifest],
    markdown_text: str,
    structured_document: dict[str, Any],
    images: list[ImageSidecar],
    ocr_remediation_applied: bool,
    pdf_audit: bool,
) -> dict[str, Any]:
    source = _source_summary(
        input_path=input_path,
        selected_manifest=selected_manifest,
        markdown_text=markdown_text,
    )
    input_type = source["input_type"]
    evidence: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "producer": _producer_metadata(),
        "source": source,
        "selected_attempt": selected_manifest["attempt"],
        "ocr_remediation_applied": ocr_remediation_applied,
        "quality": deepcopy(selected_manifest["quality"]),
        "attempts": [_apply_artifact_authority(attempt) for attempt in attempts],
        "structured_document": structured_document,
        "images": images,
        "pdf_audit": _pdf_audit_evidence(
            input_type=input_type,
            pdf_audit=pdf_audit,
        ),
    }
    if "spreadsheet" in selected_manifest:
        evidence["spreadsheet"] = deepcopy(selected_manifest["spreadsheet"])
    if "page_quality" in selected_manifest:
        evidence["page_quality"] = deepcopy(selected_manifest["page_quality"])
    return evidence
