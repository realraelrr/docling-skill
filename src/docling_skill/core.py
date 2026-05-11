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
# Keep moved names importable from docling_skill.core for compatibility.
from .constants import (
    AUTHORITATIVE_ARTIFACT,
    AVAILABLE_ARTIFACTS,
    IMAGE_TOKEN_PATTERN,
    IMAGE_PLACEHOLDER,
    INPUT_TYPE_BY_SUFFIX,
    MARKDOWN_PREFIX_PATTERN,
    MAX_OCR_NOISE_RATIO,
    MAX_TABLE_FRAGMENT_SIGNAL,
    MIN_AGENT_PAGE_TEXT_CHARACTERS,
    MIN_AGENT_TEXT_CHARACTERS,
    MIN_LINE_STRUCTURE_SIGNAL,
    OCRMAC_LANGUAGE_ALIASES,
    PREFERRED_AGENT_ARTIFACT,
    PROJECT_ROOT,
    SOURCE_DOCLING_JSON_NAME,
    SOURCE_IMAGES_NAME,
    SOURCE_MANIFEST_NAME,
    SOURCE_MARKDOWN_NAME,
    SOURCE_META_NAME,
    SPREADSHEET_INPUT_FORMATS,
    SPREADSHEET_INPUT_TYPES,
    TOKEN_PATTERN,
    TEXT_NATIVE_INPUT_FORMATS,
    TEXT_NATIVE_INPUT_TYPES,
)
from .models import AttemptArtifacts, ImageSidecar, PageArtifacts, QualityReport
from .routing import detect_input_type as _detect_input_type


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


def _picture_id(page_no: int | None, index: int) -> str:
    return _artifact_helpers._picture_id(page_no, index)


def _encode_image_base64(picture_item: Any, document: Any) -> tuple[str, str] | None:
    return _artifact_helpers._encode_image_base64(picture_item, document)


def _collect_picture_sidecars(document: Any) -> list[ImageSidecar]:
    return _artifact_helpers._collect_picture_sidecars(
        document,
        encode_image_base64=_encode_image_base64,
        picture_id_factory=_picture_id,
    )


def _group_pictures_by_page(
    pictures: list[ImageSidecar],
) -> dict[int, list[ImageSidecar]]:
    return _artifact_helpers._group_pictures_by_page(pictures)


def _inject_picture_placeholders(markdown_text: str, pictures: list[ImageSidecar]) -> str:
    return _artifact_helpers._inject_picture_placeholders(markdown_text, pictures)


def _export_structured_document(document: Any) -> dict[str, Any]:
    return _artifact_helpers._export_structured_document(document)


def _serialize_page_quality(
    page_outputs: dict[int, PageArtifacts],
) -> dict[str, QualityReport]:
    return _manifest_helpers._serialize_page_quality(page_outputs)


def _apply_artifact_authority(manifest: dict[str, Any]) -> dict[str, Any]:
    return _manifest_helpers._apply_artifact_authority(manifest)


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
) -> dict[str, Any]:
    return _manifest_helpers._build_attempt_manifest(
        pdf_path,
        input_type=input_type,
        pipeline_family=pipeline_family,
        attempt_label=attempt_label,
        status=status,
        images=images,
        markdown_text=markdown_text,
        ocr_metadata=ocr_metadata,
        quality=quality,
        page_outputs=page_outputs,
        page_count=page_count,
        remediated_pages=remediated_pages,
        serialize_page_quality=_serialize_page_quality,
        apply_artifact_authority=_apply_artifact_authority,
    )


def _finalize_selected_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    return _manifest_helpers._finalize_selected_manifest(
        manifest,
        apply_artifact_authority=_apply_artifact_authority,
    )


def _normalize_ocr_languages(ocr_languages: list[str]) -> list[str]:
    return _ocr_helpers._normalize_ocr_languages(ocr_languages)


def _normalize_engine_languages(
    ocr_engine: str,
    ocr_languages: list[str],
) -> list[str]:
    return _ocr_helpers._normalize_engine_languages(
        ocr_engine,
        ocr_languages,
        normalize_ocr_languages=_normalize_ocr_languages,
    )


def _build_ocr_options(
    ocr_engine: str,
    ocr_languages: list[str],
    force_full_page_ocr: bool,
):
    return _ocr_helpers._build_ocr_options(
        ocr_engine,
        ocr_languages,
        force_full_page_ocr,
        normalize_engine_languages=_normalize_engine_languages,
    )


def _build_ocr_metadata(
    *,
    engine: str,
    languages: list[str],
    force_full_page_ocr: bool,
    remediated_pages: list[int] | None = None,
) -> dict[str, Any]:
    return _ocr_helpers._build_ocr_metadata(
        engine=engine,
        languages=languages,
        force_full_page_ocr=force_full_page_ocr,
        remediated_pages=remediated_pages,
    )


def _build_remediation_plan(
    ocr_engine: str,
    ocr_languages: list[str],
    primary_quality: dict[str, Any],
    *,
    force_full_page_ocr: bool = False,
) -> dict[str, Any] | None:
    return _ocr_helpers._build_remediation_plan(
        ocr_engine,
        ocr_languages,
        primary_quality,
        force_full_page_ocr=force_full_page_ocr,
        build_ocr_remediation_config=_build_ocr_remediation_config,
    )


def _build_ocr_remediation_config(
    ocr_engine: str,
    ocr_languages: list[str],
    *,
    force_full_page_ocr: bool = False,
) -> dict[str, Any] | None:
    return _ocr_helpers._build_ocr_remediation_config(
        ocr_engine,
        ocr_languages,
        force_full_page_ocr=force_full_page_ocr,
        normalize_engine_languages=_normalize_engine_languages,
    )


def _build_page_remediation_plan(page_quality: dict[int, QualityReport]) -> list[int]:
    return _ocr_helpers._build_page_remediation_plan(page_quality)


def _compact_character_count(text: str) -> int:
    return _quality_helpers._compact_character_count(text)


def _strip_image_tokens(markdown_text: str) -> str:
    return _quality_helpers._strip_image_tokens(markdown_text)


def _assess_agent_quality(
    markdown_text: str,
    pictures: list[ImageSidecar],
    page_count: int,
    min_required_text: int | None = None,
) -> dict[str, Any]:
    return _quality_helpers._assess_agent_quality(
        markdown_text,
        pictures,
        page_count,
        min_required_text=min_required_text,
        strip_image_tokens=_strip_image_tokens,
        compact_character_count=_compact_character_count,
        compute_content_trust_signals=_compute_content_trust_signals,
    )


def _assess_text_native_quality(
    markdown_text: str,
    pictures: list[ImageSidecar],
    input_type: str,
) -> dict[str, Any]:
    return _quality_helpers._assess_text_native_quality(
        markdown_text,
        pictures,
        input_type,
        strip_image_tokens=_strip_image_tokens,
        compact_character_count=_compact_character_count,
        compute_text_native_structure_signals=_compute_text_native_structure_signals,
        min_text_native_characters=_min_text_native_characters,
        has_text_native_body_survival=_has_text_native_body_survival,
        compute_content_trust_signals=_compute_content_trust_signals,
    )


def _assess_spreadsheet_quality(
    markdown_text: str,
    pictures: list[ImageSidecar],
    structured_document: dict[str, Any],
) -> dict[str, Any]:
    return _quality_helpers._assess_spreadsheet_quality(
        markdown_text,
        pictures,
        structured_document,
        strip_image_tokens=_strip_image_tokens,
        compact_spreadsheet_markdown_character_count=(
            _compact_spreadsheet_markdown_character_count
        ),
        has_spreadsheet_table_content=_has_spreadsheet_table_content,
        compute_content_trust_signals=_compute_content_trust_signals,
    )


def _compact_spreadsheet_markdown_character_count(markdown_text: str) -> int:
    return _quality_helpers._compact_spreadsheet_markdown_character_count(markdown_text)


def _has_spreadsheet_table_content(structured_document: dict[str, Any]) -> bool:
    return _quality_helpers._has_spreadsheet_table_content(
        structured_document,
        compact_character_count=_compact_character_count,
    )


def _min_text_native_characters(
    input_type: str,
    *,
    structure_signals: dict[str, int | bool] | None = None,
) -> int:
    return _quality_helpers._min_text_native_characters(
        input_type,
        structure_signals=structure_signals,
        min_concise_structured_body_characters=_min_concise_structured_body_characters,
    )


def _min_text_native_body_characters(input_type: str) -> int:
    return _quality_helpers._min_text_native_body_characters(input_type)


def _min_concise_structured_body_characters(input_type: str) -> int:
    return _quality_helpers._min_concise_structured_body_characters(input_type)


def _count_lexical_tokens(lines: list[str]) -> int:
    return _quality_helpers._count_lexical_tokens(lines)


def _strip_list_marker(line: str) -> str:
    return _quality_helpers._strip_list_marker(line)


def _compute_text_native_structure_signals(
    markdown_text: str,
    *,
    input_type: str,
) -> dict[str, int | bool]:
    return _quality_helpers._compute_text_native_structure_signals(
        markdown_text,
        input_type=input_type,
        compact_character_count=_compact_character_count,
        count_lexical_tokens=_count_lexical_tokens,
        strip_list_marker=_strip_list_marker,
        min_text_native_body_characters=_min_text_native_body_characters,
        min_concise_structured_body_characters=_min_concise_structured_body_characters,
    )


def _has_text_native_body_survival(
    input_type: str,
    structure_signals: dict[str, int | bool],
) -> bool:
    return _quality_helpers._has_text_native_body_survival(input_type, structure_signals)


def _normalize_analysis_line(line: str) -> str:
    return _quality_helpers._normalize_analysis_line(line)


def _iter_content_lines(markdown_text: str) -> list[str]:
    return _quality_helpers._iter_content_lines(
        markdown_text,
        normalize_analysis_line=_normalize_analysis_line,
    )


def _is_cjk_character(character: str) -> bool:
    return _quality_helpers._is_cjk_character(character)


def _compute_ocr_noise_ratio(markdown_text: str) -> float:
    return _quality_helpers._compute_ocr_noise_ratio(
        markdown_text,
        is_suspicious_token=_is_suspicious_token,
    )


def _is_suspicious_token(token: str) -> bool:
    return _quality_helpers._is_suspicious_token(
        token,
        is_cjk_character=_is_cjk_character,
    )


def _compute_line_structure_signal(markdown_text: str) -> float:
    return _quality_helpers._compute_line_structure_signal(
        markdown_text,
        iter_content_lines=_iter_content_lines,
        compact_character_count=_compact_character_count,
        is_coherent_line=_is_coherent_line,
    )


def _is_coherent_line(line: str, line_length: int) -> bool:
    return _quality_helpers._is_coherent_line(
        line,
        line_length,
        is_cjk_character=_is_cjk_character,
    )


def _compute_table_fragment_signal(markdown_text: str) -> float:
    return _quality_helpers._compute_table_fragment_signal(
        markdown_text,
        iter_content_lines=_iter_content_lines,
        compact_character_count=_compact_character_count,
        looks_like_fragmented_table_line=_looks_like_fragmented_table_line,
    )


def _looks_like_fragmented_table_line(line: str) -> bool:
    return _quality_helpers._looks_like_fragmented_table_line(line)


def _compute_content_trust_signals(markdown_text: str) -> dict[str, float]:
    return _quality_helpers._compute_content_trust_signals(
        markdown_text,
        compute_ocr_noise_ratio=_compute_ocr_noise_ratio,
        compute_line_structure_signal=_compute_line_structure_signal,
        compute_table_fragment_signal=_compute_table_fragment_signal,
    )


def _extract_spreadsheet_metadata(
    structured_document: dict[str, Any],
    *,
    source_format: str | None = None,
    normalized_from: str | None = None,
) -> dict[str, Any]:
    return _spreadsheet_helpers._extract_spreadsheet_metadata(
        structured_document,
        source_format=source_format,
        normalized_from=normalized_from,
    )


def _spreadsheet_format_option(input_format: InputFormat):
    return _spreadsheet_helpers._spreadsheet_format_option(input_format)


def _safe_excel_sheet_title(title: str, fallback: str) -> str:
    return _spreadsheet_helpers._safe_excel_sheet_title(title, fallback)


def _xls_cell_value(book: Any, cell: Any) -> Any:
    return _spreadsheet_helpers._xls_cell_value(book, cell)


def _normalize_xls_to_xlsx(input_path: Path, output_path: Path) -> Path:
    return _spreadsheet_helpers._normalize_xls_to_xlsx(
        input_path,
        output_path,
        safe_excel_sheet_title=_safe_excel_sheet_title,
        xls_cell_value=_xls_cell_value,
    )


def _assess_page_qualities(
    page_markdown: dict[int, str],
    pictures_by_page: dict[int, list[ImageSidecar]],
) -> dict[int, QualityReport]:
    page_quality: dict[int, QualityReport] = {}

    for page_no in sorted(page_markdown):
        page_quality[page_no] = _assess_agent_quality(
            markdown_text=page_markdown[page_no],
            pictures=pictures_by_page.get(page_no, []),
            page_count=1,
            min_required_text=MIN_AGENT_PAGE_TEXT_CHARACTERS,
        )

    return page_quality


def _collect_page_outputs(
    result: Any,
    pictures: list[ImageSidecar],
    full_markdown_text: str,
) -> dict[int, PageArtifacts]:
    pictures_by_page = _group_pictures_by_page(pictures)
    raw_page_markdown = _export_page_markdown(result)
    single_page_result = len(result.pages) == 1

    page_markdown: dict[int, str] = {}
    for page in result.pages:
        page_no = page.page_no
        raw_markdown = raw_page_markdown.get(page_no, "")
        if single_page_result and not raw_markdown.strip() and full_markdown_text.strip():
            page_markdown[page_no] = full_markdown_text
        else:
            page_markdown[page_no] = _inject_picture_placeholders(
                raw_markdown,
                pictures_by_page.get(page_no, []),
            )

    page_quality = _assess_page_qualities(
        page_markdown=page_markdown,
        pictures_by_page=pictures_by_page,
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
    quality = _assess_agent_quality(
        markdown_text=markdown_text,
        pictures=images,
        page_count=len(ordered_page_nos),
    )
    structured_document = _merge_page_structured_documents(
        page_outputs,
        fallback_document=fallback_document,
        original_document_name=original_document_name,
    )
    manifest = _build_attempt_manifest(
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
    return _export_structured_document(merged_document)


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
    pages_to_remediate = _build_page_remediation_plan(
        _manifest_page_quality(primary_attempt.manifest)
    )
    remediation_plan = _build_remediation_plan(
        ocr_engine=ocr_engine,
        ocr_languages=ocr_languages,
        primary_quality=primary_attempt.manifest["quality"],
        force_full_page_ocr=force_full_page_ocr,
    )
    if remediation_plan is None and pages_to_remediate:
        remediation_plan = _build_ocr_remediation_config(
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
        remediation_ocr_metadata=_build_ocr_metadata(
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
    normalized_languages = _normalize_engine_languages(ocr_engine, ocr_languages)
    ocr_options = _build_ocr_options(
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

    pictures = _collect_picture_sidecars(result.document)
    markdown_text = result.document.export_to_markdown(image_mode=ImageRefMode.PLACEHOLDER)
    markdown_text = _inject_picture_placeholders(markdown_text, pictures)
    structured_document = _export_structured_document(result.document)
    page_outputs = _collect_page_outputs(result, pictures, markdown_text)
    quality = _assess_agent_quality(
        markdown_text=markdown_text,
        pictures=pictures,
        page_count=len(result.pages),
    )

    manifest = _build_attempt_manifest(
        pdf_path,
        input_type="pdf",
        pipeline_family="standard_pdf",
        attempt_label=attempt_label,
        status=result.status.value,
        images=pictures,
        markdown_text=markdown_text,
        ocr_metadata=_build_ocr_metadata(
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

    pictures = _collect_picture_sidecars(result.document)
    markdown_text = result.document.export_to_markdown(image_mode=ImageRefMode.PLACEHOLDER)
    markdown_text = _inject_picture_placeholders(markdown_text, pictures)
    structured_document = _export_structured_document(result.document)
    quality = _assess_text_native_quality(
        markdown_text=markdown_text,
        pictures=pictures,
        input_type=input_type,
    )
    manifest = _build_attempt_manifest(
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
            conversion_path = _normalize_xls_to_xlsx(
                input_path,
                Path(temp_dir.name) / f"{input_path.stem}.xlsx",
            )

        input_format = SPREADSHEET_INPUT_FORMATS[conversion_input_type]
        converter = DocumentConverter(
            allowed_formats=[input_format],
            format_options={
                input_format: _spreadsheet_format_option(input_format),
            },
        )
        result = converter.convert(str(conversion_path))
        if result.status not in {ConversionStatus.SUCCESS, ConversionStatus.PARTIAL_SUCCESS}:
            raise RuntimeError(f"Conversion failed with status: {result.status}")

        pictures = _collect_picture_sidecars(result.document)
        markdown_text = result.document.export_to_markdown(image_mode=ImageRefMode.PLACEHOLDER)
        markdown_text = _inject_picture_placeholders(markdown_text, pictures)
        structured_document = _export_structured_document(result.document)
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()

    spreadsheet_metadata = _extract_spreadsheet_metadata(
        structured_document,
        source_format=input_type,
        normalized_from=normalized_from,
    )
    quality = _assess_spreadsheet_quality(
        markdown_text=markdown_text,
        pictures=pictures,
        structured_document=structured_document,
    )
    manifest = _build_attempt_manifest(
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
    normalized_languages = _normalize_ocr_languages(ocr_languages or [])
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

    markdown_path.write_text(selected_attempt.markdown_text, encoding="utf-8")
    docling_json_path.write_text(
        json.dumps(selected_attempt.structured_document, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    images_path.write_text(
        json.dumps(selected_attempt.images, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    manifest = {
        **_finalize_selected_manifest(selected_attempt.manifest),
        "attempts": [_apply_artifact_authority(attempt) for attempt in attempts],
        "selected_attempt": selected_attempt.manifest["attempt"],
        "ocr_remediation_applied": len(attempts) > 1,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    meta = build_source_meta(
        input_path=input_path,
        manifest=manifest,
        markdown_text=selected_attempt.markdown_text,
        job_id=job_id,
    )
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
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
