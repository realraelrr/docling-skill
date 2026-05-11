"""OCR option and remediation helpers for ingestion outputs."""

from __future__ import annotations

from typing import Any

from docling.datamodel.pipeline_options import (
    OcrAutoOptions,
    OcrMacOptions,
    RapidOcrOptions,
    TesseractCliOcrOptions,
)

from .constants import OCRMAC_LANGUAGE_ALIASES
from .models import QualityReport


def _normalize_ocr_languages(ocr_languages: list[str]) -> list[str]:
    normalized: list[str] = []
    for language in ocr_languages:
        for token in language.split(","):
            token = token.strip()
            if token:
                normalized.append(token)
    return normalized


def _normalize_engine_languages(
    ocr_engine: str,
    ocr_languages: list[str],
    *,
    normalize_ocr_languages=_normalize_ocr_languages,
) -> list[str]:
    normalized_languages = normalize_ocr_languages(ocr_languages)
    if ocr_engine != "ocrmac":
        return normalized_languages
    return [OCRMAC_LANGUAGE_ALIASES.get(language, language) for language in normalized_languages]


def _build_ocr_options(
    ocr_engine: str,
    ocr_languages: list[str],
    force_full_page_ocr: bool,
    *,
    normalize_engine_languages=_normalize_engine_languages,
):
    normalized_languages = normalize_engine_languages(ocr_engine, ocr_languages)
    engine = ocr_engine

    if engine == "auto" and normalized_languages:
        engine = "ocrmac" if any("-" in lang for lang in normalized_languages) else "tesseract"

    if engine == "tesseract":
        return TesseractCliOcrOptions(
            lang=normalized_languages or ["eng"],
            force_full_page_ocr=force_full_page_ocr,
        )
    if engine == "ocrmac":
        return OcrMacOptions(
            lang=normalized_languages or ["en-US"],
            force_full_page_ocr=force_full_page_ocr,
        )
    if engine == "rapidocr":
        return RapidOcrOptions(
            lang=normalized_languages or ["english", "chinese"],
            force_full_page_ocr=force_full_page_ocr,
        )

    return OcrAutoOptions(force_full_page_ocr=force_full_page_ocr)


def _build_ocr_metadata(
    *,
    engine: str,
    languages: list[str],
    force_full_page_ocr: bool,
    remediated_pages: list[int] | None = None,
) -> dict[str, Any]:
    metadata = {
        "enabled": True,
        "engine": engine,
        "languages": languages,
        "force_full_page_ocr": force_full_page_ocr,
    }
    if remediated_pages:
        metadata["page_level_remediation"] = {
            "enabled": True,
            "pages": remediated_pages,
        }
    return metadata


def _build_remediation_plan(
    ocr_engine: str,
    ocr_languages: list[str],
    primary_quality: dict[str, Any],
    *,
    force_full_page_ocr: bool = False,
    build_ocr_remediation_config=None,
) -> dict[str, Any] | None:
    if primary_quality.get("agent_ready"):
        return None
    if build_ocr_remediation_config is None:
        build_ocr_remediation_config = _build_ocr_remediation_config
    return build_ocr_remediation_config(
        ocr_engine=ocr_engine,
        ocr_languages=ocr_languages,
        force_full_page_ocr=force_full_page_ocr,
    )


def _build_ocr_remediation_config(
    ocr_engine: str,
    ocr_languages: list[str],
    *,
    force_full_page_ocr: bool = False,
    normalize_engine_languages=_normalize_engine_languages,
) -> dict[str, Any] | None:
    if force_full_page_ocr:
        return None

    remediation_engine = "tesseract" if ocr_engine in {"auto", "ocrmac"} else ocr_engine
    remediation_languages = normalize_engine_languages(remediation_engine, ocr_languages)
    if not remediation_languages and remediation_engine == "tesseract":
        remediation_languages = ["eng"]

    return {
        "attempt_label": "ocr_remediation",
        "ocr_engine": remediation_engine,
        "ocr_languages": remediation_languages,
        "force_full_page_ocr": True,
    }


def _build_page_remediation_plan(page_quality: dict[int, QualityReport]) -> list[int]:
    return [
        page_no
        for page_no, quality in sorted(page_quality.items())
        if not quality.get("agent_ready", False)
    ]
