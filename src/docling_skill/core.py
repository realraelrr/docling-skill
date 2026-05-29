"""Core extraction logic for agent-friendly local document ingestion outputs."""

from __future__ import annotations

import json
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from docling.document_converter import (
    DocumentConverter,
    PdfFormatOption,
)
from docling.datamodel.base_models import ConversionStatus, InputFormat
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
)
from docling_core.types.doc import ImageRefMode
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.legacy_doc.base import Ref
from docling_core.utils.legacy import docling_document_to_legacy

from . import artifacts as _artifact_helpers
from . import manifest as _manifest_helpers
from . import ocr as _ocr_helpers
from . import quality as _quality_helpers
from . import spreadsheet as _spreadsheet_helpers
from . import text_normalization as _text_normalization_helpers
from .constants import (
    MIN_AGENT_PAGE_TEXT_CHARACTERS,
    PROJECT_ROOT,
    SOURCE_DOCLING_JSON_NAME,
    SOURCE_IMAGES_NAME,
    SOURCE_MANIFEST_NAME,
    SOURCE_MARKDOWN_NAME,
    SOURCE_META_NAME,
    SPREADSHEET_INPUT_FORMATS,
    SPREADSHEET_INPUT_TYPES,
    TEXT_NATIVE_INPUT_FORMATS,
    TEXT_NATIVE_INPUT_TYPES,
)
from .models import AttemptArtifacts, ImageSidecar, PageArtifacts, QualityReport
from .routing import detect_input_type as _detect_input_type

__all__ = [
    "convert_document_to_ingestion_outputs",
    "convert_pdf_to_sidecar_outputs",
    "build_source_meta",
    "detect_input_type",
    "infer_source_title",
]

SOURCE_SIDECAR_NAMES = (
    SOURCE_MARKDOWN_NAME,
    SOURCE_DOCLING_JSON_NAME,
    SOURCE_IMAGES_NAME,
    SOURCE_MANIFEST_NAME,
    SOURCE_META_NAME,
)


EMPTY_TEXT_NORMALIZATION_REPORT = {
    "applied": False,
    "cjk_compatibility_replacement_count": 0,
    "cjk_space_merge_count": 0,
}


def _normalize_agent_markdown(markdown_text: str) -> tuple[str, dict[str, Any]]:
    return _text_normalization_helpers.normalize_agent_markdown(markdown_text)


def _aggregate_page_text_normalization(page_outputs: dict[int, PageArtifacts]) -> dict[str, Any]:
    aggregate = dict(EMPTY_TEXT_NORMALIZATION_REPORT)
    for page_output in page_outputs.values():
        signal = page_output.quality.get("signals", {}).get("text_normalization", {})
        aggregate["cjk_compatibility_replacement_count"] += signal.get(
            "cjk_compatibility_replacement_count",
            0,
        )
        aggregate["cjk_space_merge_count"] += signal.get("cjk_space_merge_count", 0)
    aggregate["applied"] = bool(
        aggregate["cjk_compatibility_replacement_count"]
        or aggregate["cjk_space_merge_count"]
    )
    return aggregate


def detect_input_type(input_path: Path) -> str:
    return _detect_input_type(input_path)


def infer_source_title(markdown_text: str, input_path: Path) -> str:
    return _manifest_helpers.infer_source_title(markdown_text, input_path)


def build_source_meta(
    *,
    input_path: Path | str,
    manifest: dict[str, Any],
    markdown_text: str,
    job_id: str | None = None,
    source_title: str | None = None,
) -> dict[str, Any]:
    return _manifest_helpers.build_source_meta(
        input_path=input_path,
        manifest=manifest,
        markdown_text=markdown_text,
        job_id=job_id,
        source_title=source_title,
        detect_input_type_func=detect_input_type,
        infer_source_title_func=infer_source_title,
    )


def _assess_page_qualities(
    page_markdown: dict[int, str],
    pictures_by_page: dict[int, list[ImageSidecar]],
    normalization_by_page: dict[int, dict[str, Any]],
) -> dict[int, QualityReport]:
    page_quality: dict[int, QualityReport] = {}

    for page_no in sorted(page_markdown):
        page_quality[page_no] = _quality_helpers._assess_agent_quality(
            markdown_text=page_markdown[page_no],
            pictures=pictures_by_page.get(page_no, []),
            page_count=1,
            min_required_text=MIN_AGENT_PAGE_TEXT_CHARACTERS,
        )
        page_quality[page_no] = _quality_helpers._apply_text_normalization_signal(
            page_quality[page_no],
            normalization_by_page.get(page_no, EMPTY_TEXT_NORMALIZATION_REPORT),
        )

    return page_quality


def _collect_page_outputs(
    result: Any,
    pictures: list[ImageSidecar],
    full_markdown_text: str,
) -> dict[int, PageArtifacts]:
    pictures_by_page = _artifact_helpers._group_pictures_by_page(pictures)
    raw_page_markdown = _export_page_markdown(result)
    single_page_result = len(result.pages) == 1

    page_markdown: dict[int, str] = {}
    normalization_by_page: dict[int, dict[str, Any]] = {}
    for page in result.pages:
        page_no = page.page_no
        raw_markdown = raw_page_markdown.get(page_no, "")
        if single_page_result and not raw_markdown.strip() and full_markdown_text.strip():
            page_text = full_markdown_text
        else:
            page_text = _artifact_helpers._inject_picture_placeholders(
                raw_markdown,
                pictures_by_page.get(page_no, []),
            )
        page_markdown[page_no], normalization_by_page[page_no] = _normalize_agent_markdown(page_text)

    page_quality = _assess_page_qualities(
        page_markdown=page_markdown,
        pictures_by_page=pictures_by_page,
        normalization_by_page=normalization_by_page,
    )

    return {
        page_no: PageArtifacts(
            markdown_text=page_markdown[page_no],
            images=pictures_by_page.get(page_no, []),
            quality=page_quality[page_no],
        )
        for page_no in sorted(page_markdown)
    }


def _export_page_markdown(result: Any) -> dict[int, str]:
    doc = docling_document_to_legacy(result.document)
    if doc.main_text is None:
        return {}

    start_ix = 0
    end_ix = 0
    current_page_no = 0
    has_items = False
    page_markdown: dict[int, str] = {}

    def flush_page(page_no: int, start: int, end: int) -> None:
        page_markdown[page_no] = doc.export_to_markdown(
            main_text_start=start,
            main_text_stop=end + 1,
        )

    for ix, original_item in enumerate(doc.main_text):
        item = doc._resolve_ref(original_item) if isinstance(original_item, Ref) else original_item
        if item is None or item.prov is None or len(item.prov) == 0:
            continue

        item_page_no = item.prov[0].page
        if current_page_no > 0 and item_page_no > current_page_no:
            flush_page(current_page_no, start_ix, end_ix)
            start_ix = ix

        current_page_no = item_page_no
        end_ix = ix
        has_items = True

    if has_items and current_page_no > 0:
        flush_page(current_page_no, start_ix, end_ix)

    return page_markdown


def _assemble_attempt_from_pages(
    pdf_path: Path,
    *,
    page_outputs: dict[int, PageArtifacts],
    fallback_document: DoclingDocument,
    original_document_name: str,
    attempt_label: str,
    status: str,
    ocr_metadata: dict[str, Any],
    remediated_pages: list[int] | None = None,
) -> AttemptArtifacts:
    ordered_page_nos = sorted(page_outputs)
    markdown_chunks = [
        page_outputs[page_no].markdown_text
        for page_no in ordered_page_nos
        if page_outputs[page_no].markdown_text
    ]
    markdown_text = "\n\n".join(markdown_chunks)
    images = [
        image
        for page_no in ordered_page_nos
        for image in page_outputs[page_no].images
    ]
    quality = _quality_helpers._assess_agent_quality(
        markdown_text=markdown_text,
        pictures=images,
        page_count=len(ordered_page_nos),
    )
    quality = _quality_helpers._apply_page_quality_risk(
        quality,
        {
            page_no: page_outputs[page_no].quality
            for page_no in ordered_page_nos
        },
    )
    quality = _quality_helpers._apply_text_normalization_signal(
        quality,
        _aggregate_page_text_normalization(page_outputs),
    )
    structured_document = _merge_page_structured_documents(
        page_outputs,
        fallback_document=fallback_document,
        original_document_name=original_document_name,
    )
    manifest = _manifest_helpers._build_attempt_manifest(
        pdf_path,
        input_type="pdf",
        pipeline_family="standard_pdf",
        attempt_label=attempt_label,
        status=status,
        images=images,
        markdown_text=markdown_text,
        ocr_metadata=ocr_metadata,
        quality=quality,
        page_outputs=page_outputs,
        remediated_pages=remediated_pages,
    )
    return AttemptArtifacts(
        markdown_text=markdown_text,
        images=images,
        page_outputs=page_outputs,
        structured_document=deepcopy(structured_document),
        manifest=manifest,
    )


def _merge_page_attempts(
    primary_attempt: AttemptArtifacts,
    remediated_pages: dict[int, PageArtifacts],
    remediation_ocr_metadata: dict[str, Any],
) -> AttemptArtifacts:
    merged_page_outputs = deepcopy(primary_attempt.page_outputs)
    for page_no, remediated_page in remediated_pages.items():
        merged_page_outputs[page_no] = remediated_page

    merged_ocr = {
        **deepcopy(remediation_ocr_metadata),
        "page_level_remediation": {
            "enabled": True,
            "pages": sorted(remediated_pages),
        },
    }
    primary_document = DoclingDocument.model_validate(primary_attempt.structured_document)

    return _assemble_attempt_from_pages(
        Path(primary_attempt.manifest["source_file"]),
        page_outputs=merged_page_outputs,
        fallback_document=primary_document,
        original_document_name=primary_document.name,
        attempt_label="page_ocr_remediation",
        status=primary_attempt.manifest["status"],
        ocr_metadata=merged_ocr,
        remediated_pages=sorted(remediated_pages),
    )


def _merge_page_structured_documents(
    page_outputs: dict[int, PageArtifacts],
    *,
    fallback_document: DoclingDocument,
    original_document_name: str,
) -> dict[str, Any]:
    ordered_page_documents = [
        (
            DoclingDocument.model_validate(page_outputs[page_no].structured_document)
            if page_outputs[page_no].structured_document is not None
            else fallback_document.filter(page_nrs={page_no})
        )
        for page_no in sorted(page_outputs)
    ]
    merged_document = (
        ordered_page_documents[0]
        if len(ordered_page_documents) == 1
        else DoclingDocument.concatenate(ordered_page_documents)
    )
    merged_document.name = original_document_name
    return _artifact_helpers._export_structured_document(merged_document)


def _pick_better_attempt(
    primary_attempt: AttemptArtifacts,
    candidate_attempt: AttemptArtifacts,
) -> AttemptArtifacts:
    primary_quality = primary_attempt.manifest["quality"]
    candidate_quality = candidate_attempt.manifest["quality"]

    if candidate_quality["agent_ready"] and not primary_quality["agent_ready"]:
        return candidate_attempt
    if primary_quality["agent_ready"] and not candidate_quality["agent_ready"]:
        return primary_attempt
    if (
        candidate_quality["non_placeholder_characters"]
        > primary_quality["non_placeholder_characters"]
    ):
        return candidate_attempt
    return primary_attempt


def _manifest_page_quality(manifest: dict[str, Any]) -> dict[int, QualityReport]:
    return {
        int(page_no): quality
        for page_no, quality in manifest["page_quality"].items()
    }


def _select_remediation_plan(
    *,
    primary_attempt: AttemptArtifacts,
    ocr_engine: str,
    ocr_languages: list[str],
    force_full_page_ocr: bool,
) -> tuple[list[int], dict[str, Any] | None]:
    pages_to_remediate = _ocr_helpers._build_page_remediation_plan(
        _manifest_page_quality(primary_attempt.manifest)
    )
    remediation_plan = _ocr_helpers._build_remediation_plan(
        ocr_engine=ocr_engine,
        ocr_languages=ocr_languages,
        primary_quality=primary_attempt.manifest["quality"],
        force_full_page_ocr=force_full_page_ocr,
    )
    if remediation_plan is None and pages_to_remediate:
        remediation_plan = _ocr_helpers._build_ocr_remediation_config(
            ocr_engine=ocr_engine,
            ocr_languages=ocr_languages,
            force_full_page_ocr=force_full_page_ocr,
        )
    return pages_to_remediate, remediation_plan


def _remediate_pages(
    pdf_path: Path,
    *,
    primary_attempt: AttemptArtifacts,
    remediation_plan: dict[str, Any],
    pages_to_remediate: list[int],
) -> AttemptArtifacts | None:
    remediated_pages: dict[int, PageArtifacts] = {}

    for page_no in pages_to_remediate:
        remediated_page_attempt = _convert_single_attempt(
            pdf_path,
            ocr_engine=remediation_plan["ocr_engine"],
            ocr_languages=remediation_plan["ocr_languages"],
            force_full_page_ocr=remediation_plan["force_full_page_ocr"],
            attempt_label=remediation_plan["attempt_label"],
            page_range=(page_no, page_no),
        )
        remediated_page = deepcopy(remediated_page_attempt.page_outputs[page_no])
        remediated_page.structured_document = remediated_page_attempt.structured_document
        remediated_pages[page_no] = remediated_page

    if not remediated_pages:
        return None

    return _merge_page_attempts(
        primary_attempt,
        remediated_pages,
        remediation_ocr_metadata=_ocr_helpers._build_ocr_metadata(
            engine=remediation_plan["ocr_engine"],
            languages=remediation_plan["ocr_languages"],
            force_full_page_ocr=remediation_plan["force_full_page_ocr"],
        ),
    )


def _convert_single_attempt(
    pdf_path: Path,
    *,
    ocr_engine: str,
    ocr_languages: list[str],
    force_full_page_ocr: bool,
    attempt_label: str,
    page_range: tuple[int, int] | None = None,
) -> AttemptArtifacts:
    normalized_languages = _ocr_helpers._normalize_engine_languages(
        ocr_engine,
        ocr_languages,
    )
    ocr_options = _ocr_helpers._build_ocr_options(
        ocr_engine=ocr_engine,
        ocr_languages=normalized_languages,
        force_full_page_ocr=force_full_page_ocr,
    )
    effective_engine = getattr(ocr_options, "kind", ocr_engine)

    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=PdfPipelineOptions(
                    do_ocr=True,
                    ocr_options=ocr_options,
                    generate_picture_images=True,
                    images_scale=2.0,
                )
            )
        }
    )

    result = converter.convert(
        str(pdf_path),
        page_range=page_range if page_range is not None else (1, sys.maxsize),
    )
    if result.status not in {ConversionStatus.SUCCESS, ConversionStatus.PARTIAL_SUCCESS}:
        raise RuntimeError(f"Conversion failed with status: {result.status}")

    pictures = _artifact_helpers._collect_picture_sidecars(result.document)
    markdown_text = result.document.export_to_markdown(image_mode=ImageRefMode.PLACEHOLDER)
    markdown_text = _artifact_helpers._inject_picture_placeholders(markdown_text, pictures)
    markdown_text, normalization_report = _normalize_agent_markdown(markdown_text)
    structured_document = _artifact_helpers._export_structured_document(result.document)
    page_outputs = _collect_page_outputs(result, pictures, markdown_text)
    quality = _quality_helpers._assess_agent_quality(
        markdown_text=markdown_text,
        pictures=pictures,
        page_count=len(result.pages),
    )
    quality = _quality_helpers._apply_page_quality_risk(
        quality,
        {
            page_no: page_output.quality
            for page_no, page_output in page_outputs.items()
        },
    )
    quality = _quality_helpers._apply_text_normalization_signal(
        quality,
        normalization_report,
    )

    manifest = _manifest_helpers._build_attempt_manifest(
        pdf_path,
        input_type="pdf",
        pipeline_family="standard_pdf",
        attempt_label=attempt_label,
        status=result.status.value,
        images=pictures,
        markdown_text=markdown_text,
        ocr_metadata=_ocr_helpers._build_ocr_metadata(
            engine=effective_engine,
            languages=normalized_languages,
            force_full_page_ocr=force_full_page_ocr,
        ),
        quality=quality,
        page_outputs=page_outputs,
    )

    return AttemptArtifacts(
        markdown_text=markdown_text,
        images=pictures,
        page_outputs=page_outputs,
        structured_document=structured_document,
        manifest=manifest,
    )


def _convert_pdf_input(
    input_path: Path,
    *,
    ocr_engine: str,
    ocr_languages: list[str],
    force_full_page_ocr: bool,
    ocr_remediation: bool,
) -> tuple[AttemptArtifacts, list[dict[str, Any]]]:
    primary_attempt = _convert_single_attempt(
        input_path,
        ocr_engine=ocr_engine,
        ocr_languages=ocr_languages,
        force_full_page_ocr=force_full_page_ocr,
        attempt_label="primary",
    )
    attempts = [primary_attempt.manifest]
    selected_attempt = primary_attempt

    if ocr_remediation:
        pages_to_remediate, remediation_plan = _select_remediation_plan(
            primary_attempt=primary_attempt,
            ocr_engine=ocr_engine,
            ocr_languages=ocr_languages,
            force_full_page_ocr=force_full_page_ocr,
        )
        if remediation_plan is not None:
            remediated_attempt = _remediate_pages(
                input_path,
                primary_attempt=primary_attempt,
                remediation_plan=remediation_plan,
                pages_to_remediate=pages_to_remediate,
            )
            if remediated_attempt is not None:
                attempts.append(remediated_attempt.manifest)
                selected_attempt = _pick_better_attempt(primary_attempt, remediated_attempt)

    return selected_attempt, attempts


def _convert_text_native_input(
    input_path: Path,
    *,
    input_type: str,
) -> tuple[AttemptArtifacts, list[dict[str, Any]]]:
    converter = DocumentConverter(
        allowed_formats=[TEXT_NATIVE_INPUT_FORMATS[input_type]]
    )
    if input_type == "txt":
        result = converter.convert_string(
            input_path.read_text(encoding="utf-8"),
            format=InputFormat.MD,
            name=f"{input_path.stem}.md",
        )
    else:
        result = converter.convert(str(input_path))
    if result.status not in {ConversionStatus.SUCCESS, ConversionStatus.PARTIAL_SUCCESS}:
        raise RuntimeError(f"Conversion failed with status: {result.status}")

    pictures = _artifact_helpers._collect_picture_sidecars(result.document)
    markdown_text = result.document.export_to_markdown(image_mode=ImageRefMode.PLACEHOLDER)
    markdown_text = _artifact_helpers._inject_picture_placeholders(markdown_text, pictures)
    markdown_text, normalization_report = _normalize_agent_markdown(markdown_text)
    structured_document = _artifact_helpers._export_structured_document(result.document)
    quality = _quality_helpers._assess_text_native_quality(
        markdown_text=markdown_text,
        pictures=pictures,
        input_type=input_type,
    )
    quality = _quality_helpers._apply_text_normalization_signal(
        quality,
        normalization_report,
    )
    manifest = _manifest_helpers._build_attempt_manifest(
        input_path,
        input_type=input_type,
        pipeline_family="simple",
        attempt_label="primary",
        status=result.status.value,
        images=pictures,
        markdown_text=markdown_text,
        ocr_metadata=None,
        quality=quality,
        page_outputs={},
        page_count=max(len(getattr(result, "pages", [])), 1),
    )
    attempt = AttemptArtifacts(
        markdown_text=markdown_text,
        images=pictures,
        page_outputs={},
        structured_document=structured_document,
        manifest=manifest,
    )
    return attempt, [attempt.manifest]


def _convert_spreadsheet_input(
    input_path: Path,
    *,
    input_type: str,
) -> tuple[AttemptArtifacts, list[dict[str, Any]]]:
    normalized_from = None
    conversion_input_type = input_type
    conversion_path = input_path
    temp_dir: tempfile.TemporaryDirectory[str] | None = None

    try:
        if input_type == "xls":
            temp_dir = tempfile.TemporaryDirectory()
            normalized_from = "xls"
            conversion_input_type = "xlsx"
            conversion_path = _spreadsheet_helpers._normalize_xls_to_xlsx(
                input_path,
                Path(temp_dir.name) / f"{input_path.stem}.xlsx",
            )

        input_format = SPREADSHEET_INPUT_FORMATS[conversion_input_type]
        converter = DocumentConverter(
            allowed_formats=[input_format],
            format_options={
                input_format: _spreadsheet_helpers._spreadsheet_format_option(input_format),
            },
        )
        result = converter.convert(str(conversion_path))
        if result.status not in {ConversionStatus.SUCCESS, ConversionStatus.PARTIAL_SUCCESS}:
            raise RuntimeError(f"Conversion failed with status: {result.status}")

        pictures = _artifact_helpers._collect_picture_sidecars(result.document)
        markdown_text = result.document.export_to_markdown(image_mode=ImageRefMode.PLACEHOLDER)
        markdown_text = _artifact_helpers._inject_picture_placeholders(markdown_text, pictures)
        markdown_text, normalization_report = _normalize_agent_markdown(markdown_text)
        structured_document = _artifact_helpers._export_structured_document(result.document)
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()

    spreadsheet_metadata = _spreadsheet_helpers._extract_spreadsheet_metadata(
        structured_document,
        source_format=input_type,
        normalized_from=normalized_from,
    )
    quality = _quality_helpers._assess_spreadsheet_quality(
        markdown_text=markdown_text,
        pictures=pictures,
        structured_document=structured_document,
    )
    quality = _quality_helpers._apply_text_normalization_signal(
        quality,
        normalization_report,
    )
    manifest = _manifest_helpers._build_attempt_manifest(
        input_path,
        input_type=input_type,
        pipeline_family="spreadsheet",
        attempt_label="primary",
        status=result.status.value,
        images=pictures,
        markdown_text=markdown_text,
        ocr_metadata=None,
        quality=quality,
        page_outputs={},
        page_count=spreadsheet_metadata["sheet_count"],
    )
    manifest["spreadsheet"] = spreadsheet_metadata
    attempt = AttemptArtifacts(
        markdown_text=markdown_text,
        images=pictures,
        page_outputs={},
        structured_document=structured_document,
        manifest=manifest,
    )
    return attempt, [attempt.manifest]


def _dispatch_conversion(
    input_path: Path,
    *,
    input_type: str,
    ocr_engine: str,
    ocr_languages: list[str],
    force_full_page_ocr: bool,
    ocr_remediation: bool,
) -> tuple[AttemptArtifacts, list[dict[str, Any]]]:
    if input_type == "pdf":
        return _convert_pdf_input(
            input_path,
            ocr_engine=ocr_engine,
            ocr_languages=ocr_languages,
            force_full_page_ocr=force_full_page_ocr,
            ocr_remediation=ocr_remediation,
        )
    if input_type in TEXT_NATIVE_INPUT_TYPES:
        return _convert_text_native_input(
            input_path,
            input_type=input_type,
        )
    if input_type in SPREADSHEET_INPUT_TYPES:
        return _convert_spreadsheet_input(
            input_path,
            input_type=input_type,
        )
    if input_type == "xlsm":
        raise NotImplementedError(
            "Unsupported macro-enabled spreadsheet for v1 ingestion contract: .xlsm. "
            "Save as .xlsx or .csv before ingestion."
        )
    raise NotImplementedError(
        f"Unsupported input type for v1 ingestion contract: {input_path.suffix or '<no suffix>'}"
    )


def _preflight_sidecar_publish_targets(output_dir: Path) -> None:
    for filename in SOURCE_SIDECAR_NAMES:
        target = output_dir / filename
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise RuntimeError(
                f"Cannot publish sidecar {target}: target is not a regular file"
            )


def _write_sidecars_with_staging(
    output_dir: Path,
    *,
    markdown_text: str,
    structured_document: dict[str, Any],
    images: list[ImageSidecar],
    manifest: dict[str, Any],
    meta: dict[str, Any],
) -> None:
    _preflight_sidecar_publish_targets(output_dir)

    with tempfile.TemporaryDirectory(prefix=".docling-skill-", dir=output_dir) as tmp_dir:
        staging_dir = Path(tmp_dir)
        (staging_dir / SOURCE_MARKDOWN_NAME).write_text(markdown_text, encoding="utf-8")
        (staging_dir / SOURCE_DOCLING_JSON_NAME).write_text(
            json.dumps(structured_document, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (staging_dir / SOURCE_IMAGES_NAME).write_text(
            json.dumps(images, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (staging_dir / SOURCE_MANIFEST_NAME).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (staging_dir / SOURCE_META_NAME).write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        _preflight_sidecar_publish_targets(output_dir)
        for filename in SOURCE_SIDECAR_NAMES:
            (staging_dir / filename).replace(output_dir / filename)


def convert_document_to_ingestion_outputs(
    input_path: Path,
    output_dir: Path,
    *,
    ocr_engine: str = "auto",
    ocr_languages: list[str] | None = None,
    force_full_page_ocr: bool = False,
    ocr_remediation: bool = True,
    job_id: str | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    normalized_languages = _ocr_helpers._normalize_ocr_languages(ocr_languages or [])
    input_type = detect_input_type(input_path)

    selected_attempt, attempts = _dispatch_conversion(
        input_path,
        input_type=input_type,
        ocr_engine=ocr_engine,
        ocr_languages=normalized_languages,
        force_full_page_ocr=force_full_page_ocr,
        ocr_remediation=ocr_remediation,
    )

    markdown_path = output_dir / SOURCE_MARKDOWN_NAME
    docling_json_path = output_dir / SOURCE_DOCLING_JSON_NAME
    images_path = output_dir / SOURCE_IMAGES_NAME
    manifest_path = output_dir / SOURCE_MANIFEST_NAME
    meta_path = output_dir / SOURCE_META_NAME

    manifest = {
        **_manifest_helpers._finalize_selected_manifest(selected_attempt.manifest),
        "attempts": [_manifest_helpers._apply_artifact_authority(attempt) for attempt in attempts],
        "selected_attempt": selected_attempt.manifest["attempt"],
        "ocr_remediation_applied": len(attempts) > 1,
    }
    meta = build_source_meta(
        input_path=input_path,
        manifest=manifest,
        markdown_text=selected_attempt.markdown_text,
        job_id=job_id,
    )

    _write_sidecars_with_staging(
        output_dir,
        markdown_text=selected_attempt.markdown_text,
        structured_document=selected_attempt.structured_document,
        images=selected_attempt.images,
        manifest=manifest,
        meta=meta,
    )

    return {
        "markdown_path": markdown_path,
        "docling_json_path": docling_json_path,
        "images_path": images_path,
        "manifest_path": manifest_path,
        "meta_path": meta_path,
        "markdown_text": selected_attempt.markdown_text,
        "docling_document": selected_attempt.structured_document,
        "images": selected_attempt.images,
        "manifest": manifest,
        "meta": meta,
    }


def convert_pdf_to_sidecar_outputs(
    pdf_path: Path,
    output_dir: Path,
    *,
    ocr_engine: str = "auto",
    ocr_languages: list[str] | None = None,
    force_full_page_ocr: bool = False,
    ocr_remediation: bool = True,
    job_id: str | None = None,
) -> dict[str, Any]:
    return convert_document_to_ingestion_outputs(
        input_path=pdf_path,
        output_dir=output_dir,
        ocr_engine=ocr_engine,
        ocr_languages=ocr_languages,
        force_full_page_ocr=force_full_page_ocr,
        ocr_remediation=ocr_remediation,
        job_id=job_id,
    )
