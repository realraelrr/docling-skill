"""Core extraction logic for agent-friendly local document ingestion outputs."""

from __future__ import annotations

import base64
import json
import re
import sys
from copy import deepcopy
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import ConversionStatus, InputFormat
from docling.datamodel.pipeline_options import (
    OcrAutoOptions,
    OcrMacOptions,
    PdfPipelineOptions,
    RapidOcrOptions,
    TesseractCliOcrOptions,
)
from docling_core.types.doc import ImageRefMode, PictureItem
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.legacy_doc.base import Ref
from docling_core.utils.legacy import docling_document_to_legacy

PROJECT_ROOT = Path(__file__).resolve().parents[2]
IMAGE_PLACEHOLDER = "<!-- image -->"
IMAGE_TOKEN_PATTERN = re.compile(r"\[\[image:[^\]]+\]\]")
MARKDOWN_PREFIX_PATTERN = re.compile(r"^(#{1,6}\s+|[-*+]\s+|\d+\.\s+)")
TOKEN_PATTERN = re.compile(r"[^\s]+")
SOURCE_MARKDOWN_NAME = "source.md"
SOURCE_DOCLING_JSON_NAME = "source.docling.json"
SOURCE_IMAGES_NAME = "source.images.json"
SOURCE_MANIFEST_NAME = "source.manifest.json"
SOURCE_META_NAME = "source.meta.json"
AVAILABLE_ARTIFACTS = [
    SOURCE_MARKDOWN_NAME,
    SOURCE_DOCLING_JSON_NAME,
    SOURCE_IMAGES_NAME,
]
PREFERRED_AGENT_ARTIFACT = SOURCE_MARKDOWN_NAME
AUTHORITATIVE_ARTIFACT = SOURCE_DOCLING_JSON_NAME
MIN_AGENT_TEXT_CHARACTERS = 120
MIN_AGENT_PAGE_TEXT_CHARACTERS = 40
MAX_OCR_NOISE_RATIO = 0.25
MIN_LINE_STRUCTURE_SIGNAL = 0.35
MAX_TABLE_FRAGMENT_SIGNAL = 0.45
OCRMAC_LANGUAGE_ALIASES = {
    "zh-CN": "zh-Hans",
    "zh-SG": "zh-Hans",
    "zh-TW": "zh-Hant",
    "zh-HK": "zh-Hant",
    "en": "en-US",
}
INPUT_TYPE_BY_SUFFIX = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".pptx": "pptx",
    ".xlsx": "xlsx",
    ".html": "html",
    ".htm": "html",
    ".txt": "txt",
    ".md": "md",
    ".tex": "latex",
    ".vtt": "webvtt",
    ".wav": "wav",
    ".mp3": "mp3",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".gif": "image",
    ".webp": "image",
}
TEXT_NATIVE_INPUT_TYPES = {"docx", "html", "txt", "md"}
TEXT_NATIVE_INPUT_FORMATS = {
    "docx": InputFormat.DOCX,
    "html": InputFormat.HTML,
    "txt": InputFormat.MD,
    "md": InputFormat.MD,
}

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


def _compact_character_count(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def detect_input_type(input_path: Path) -> str:
    return INPUT_TYPE_BY_SUFFIX.get(input_path.suffix.lower(), "document")


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
    manifest: dict[str, Any],
    markdown_text: str,
    job_id: str | None = None,
    source_title: str | None = None,
) -> dict[str, Any]:
    normalized_input_path = Path(input_path)
    quality = manifest["quality"]

    return {
        "job_id": job_id,
        "input_type": manifest.get("input_type", detect_input_type(normalized_input_path)),
        "source_title": source_title or infer_source_title(markdown_text, normalized_input_path),
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


def _picture_id(page_no: int | None, index: int) -> str:
    normalized_page_no = page_no if page_no is not None else 0
    return f"picture-p{normalized_page_no}-{index}"


def _encode_image_base64(picture_item: PictureItem, document: Any) -> tuple[str, str] | None:
    image = picture_item.get_image(document)
    if image is None:
        return None

    image_buffer = BytesIO()
    image.save(image_buffer, format="PNG")
    return "image/png", base64.b64encode(image_buffer.getvalue()).decode("utf-8")


def _collect_picture_sidecars(document: Any) -> list[ImageSidecar]:
    pictures: list[ImageSidecar] = []
    picture_indices_by_page: dict[int, int] = {}

    for item, _level in document.iterate_items(traverse_pictures=True):
        if not isinstance(item, PictureItem):
            continue

        encoded = _encode_image_base64(item, document)
        if encoded is None:
            continue

        mime_type, image_base64 = encoded
        prov = item.prov[0] if item.prov else None
        page_no = getattr(prov, "page_no", None)
        page_index = picture_indices_by_page.get(page_no or 0, 0)
        picture_indices_by_page[page_no or 0] = page_index + 1

        picture_id = _picture_id(page_no, page_index)
        placeholder = f"[[image:{picture_id}]]"

        pictures.append(
            {
                "id": picture_id,
                "placeholder": placeholder,
                "self_ref": getattr(item, "self_ref", None),
                "page_no": getattr(prov, "page_no", None),
                "bbox": prov.bbox.model_dump() if prov and getattr(prov, "bbox", None) else None,
                "caption_refs": [caption.cref for caption in item.captions],
                "mime_type": mime_type,
                "base64": image_base64,
            }
        )

    return pictures


def _group_pictures_by_page(
    pictures: list[ImageSidecar],
) -> dict[int, list[ImageSidecar]]:
    pictures_by_page: dict[int, list[ImageSidecar]] = {}
    for picture in pictures:
        page_no = picture.get("page_no")
        if page_no is None:
            continue
        pictures_by_page.setdefault(page_no, []).append(picture)
    return pictures_by_page


def _inject_picture_placeholders(markdown_text: str, pictures: list[ImageSidecar]) -> str:
    updated_markdown = markdown_text

    for picture in pictures:
        if IMAGE_PLACEHOLDER in updated_markdown:
            updated_markdown = updated_markdown.replace(
                IMAGE_PLACEHOLDER, picture["placeholder"], 1
            )
        else:
            updated_markdown += f"\n\n{picture['placeholder']}\n"

    return updated_markdown


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
) -> list[str]:
    normalized_languages = _normalize_ocr_languages(ocr_languages)
    if ocr_engine != "ocrmac":
        return normalized_languages
    return [OCRMAC_LANGUAGE_ALIASES.get(language, language) for language in normalized_languages]


def _build_ocr_options(
    ocr_engine: str,
    ocr_languages: list[str],
    force_full_page_ocr: bool,
):
    normalized_languages = _normalize_engine_languages(ocr_engine, ocr_languages)
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


def _assess_agent_quality(
    markdown_text: str,
    pictures: list[ImageSidecar],
    page_count: int,
    min_required_text: int | None = None,
) -> dict[str, Any]:
    placeholder_count = len(IMAGE_TOKEN_PATTERN.findall(markdown_text))
    text_without_placeholders = _strip_image_tokens(markdown_text)
    non_placeholder_characters = _compact_character_count(text_without_placeholders)
    required_text = (
        min_required_text
        if min_required_text is not None
        else max(MIN_AGENT_TEXT_CHARACTERS, page_count * 20)
    )
    content_trust = _compute_content_trust_signals(text_without_placeholders)

    reasons: list[str] = []
    if non_placeholder_characters < required_text:
        reasons.append("low_text_content")
    if placeholder_count > 0 and non_placeholder_characters == 0:
        reasons.append("image_only_output")
    if non_placeholder_characters >= required_text:
        if content_trust["ocr_noise_ratio"] >= MAX_OCR_NOISE_RATIO:
            reasons.append("high_ocr_noise")
        if (
            content_trust["line_structure_signal"] < MIN_LINE_STRUCTURE_SIGNAL
            and content_trust["table_fragment_signal"] >= MAX_TABLE_FRAGMENT_SIGNAL
        ):
            reasons.append("fragmented_layout")

    status = "good" if not reasons else "failed_for_agent"

    return {
        "status": status,
        "agent_ready": status == "good",
        "reasons": reasons,
        "placeholder_count": placeholder_count,
        "non_placeholder_characters": non_placeholder_characters,
        "min_required_text_characters": required_text,
        "picture_count": len(pictures),
        "content_trust": content_trust,
    }


def _assess_text_native_quality(
    markdown_text: str,
    pictures: list[ImageSidecar],
    input_type: str,
) -> dict[str, Any]:
    placeholder_count = len(IMAGE_TOKEN_PATTERN.findall(markdown_text))
    text_without_placeholders = _strip_image_tokens(markdown_text)
    non_placeholder_characters = _compact_character_count(text_without_placeholders)
    structure_signals = _compute_text_native_structure_signals(
        text_without_placeholders,
        input_type=input_type,
    )

    reasons: list[str] = []
    if non_placeholder_characters < _min_text_native_characters(
        input_type,
        structure_signals=structure_signals,
    ):
        reasons.append("low_text_content")
    if placeholder_count > 0 and non_placeholder_characters == 0:
        reasons.append("image_only_output")
    if (
        non_placeholder_characters
        >= _min_text_native_characters(input_type, structure_signals=structure_signals)
        and not _has_text_native_body_survival(input_type, structure_signals)
    ):
        reasons.append("missing_body_structure")

    status = "good" if not reasons else "failed_for_agent"

    return {
        "status": status,
        "agent_ready": status == "good",
        "reasons": reasons,
        "placeholder_count": placeholder_count,
        "non_placeholder_characters": non_placeholder_characters,
        "min_required_text_characters": _min_text_native_characters(
            input_type,
            structure_signals=structure_signals,
        ),
        "picture_count": len(pictures),
        "content_trust": _compute_content_trust_signals(text_without_placeholders),
    }


def _strip_image_tokens(markdown_text: str) -> str:
    return IMAGE_TOKEN_PATTERN.sub("", markdown_text)


def _min_text_native_characters(
    input_type: str,
    *,
    structure_signals: dict[str, int | bool] | None = None,
) -> int:
    if input_type == "txt":
        return 3
    if (
        structure_signals
        and structure_signals["has_heading"]
        and structure_signals["body_characters"] >= _min_concise_structured_body_characters(input_type)
    ):
        return 5
    return 8


def _min_text_native_body_characters(input_type: str) -> int:
    if input_type == "txt":
        return 3
    return 5


def _min_concise_structured_body_characters(input_type: str) -> int:
    if input_type == "txt":
        return 3
    return 2


def _count_lexical_tokens(lines: list[str]) -> int:
    return sum(
        1
        for line in lines
        for token in TOKEN_PATTERN.findall(line)
        if any(character.isalpha() for character in token)
    )


def _compute_text_native_structure_signals(
    markdown_text: str,
    *,
    input_type: str,
) -> dict[str, int | bool]:
    raw_lines = [line.rstrip() for line in markdown_text.splitlines()]
    content_lines = [line.strip() for line in raw_lines if line.strip()]
    heading_lines = [line for line in content_lines if re.match(r"^#{1,6}\s+\S", line)]
    list_lines = [line for line in content_lines if re.match(r"^([-*+]\s+|\d+\.\s+)", line)]
    body_lines = [
        line for line in content_lines if line not in heading_lines and line not in list_lines
    ]
    body_characters = sum(_compact_character_count(line) for line in body_lines)
    body_lexical_token_count = _count_lexical_tokens(body_lines)

    return {
        "has_heading": bool(heading_lines),
        "has_list_markers": bool(list_lines),
        "heading_count": len(heading_lines),
        "list_item_count": len(list_lines),
        "body_line_count": len(body_lines),
        "body_characters": body_characters,
        "body_lexical_token_count": body_lexical_token_count,
        "paragraph_survival": bool(body_lines)
        and (
            body_characters >= _min_text_native_body_characters(input_type)
            or (
                bool(heading_lines)
                and body_characters >= _min_concise_structured_body_characters(input_type)
                and body_lexical_token_count >= 1
            )
        ),
        "list_survival": len(list_lines) >= 1,
    }


def _has_text_native_body_survival(
    input_type: str,
    structure_signals: dict[str, int | bool],
) -> bool:
    if input_type == "txt":
        return bool(
            structure_signals["paragraph_survival"]
            or (
                structure_signals["has_list_markers"]
                and structure_signals["list_survival"]
            )
            or structure_signals["body_characters"] >= 3
        )

    return bool(
        structure_signals["paragraph_survival"]
        or (
            structure_signals["has_list_markers"]
            and structure_signals["list_survival"]
        )
    )


def _normalize_analysis_line(line: str) -> str:
    return MARKDOWN_PREFIX_PATTERN.sub("", line.strip()).strip()


def _iter_content_lines(markdown_text: str) -> list[str]:
    return [
        normalized
        for raw_line in markdown_text.splitlines()
        if (normalized := _normalize_analysis_line(raw_line))
    ]


def _is_cjk_character(character: str) -> bool:
    return "\u4e00" <= character <= "\u9fff"


def _compute_ocr_noise_ratio(markdown_text: str) -> float:
    tokens = TOKEN_PATTERN.findall(markdown_text)
    analyzable_tokens = [token for token in tokens if re.search(r"[A-Za-z0-9\u4e00-\u9fff]", token)]
    if not analyzable_tokens:
        return 0.0

    suspicious_count = sum(1 for token in analyzable_tokens if _is_suspicious_token(token))
    return suspicious_count / len(analyzable_tokens)


def _is_suspicious_token(token: str) -> bool:
    core = token.strip(".,;:!?()[]{}<>\"'`|/\\+-=_~")
    if not core:
        return False

    letters = sum(character.isalpha() for character in core)
    digits = sum(character.isdigit() for character in core)
    cjk = sum(_is_cjk_character(character) for character in core)
    punctuation = len(core) - letters - digits - cjk
    latin_letters = [character for character in core if character.isalpha() and not _is_cjk_character(character)]
    uppercase_count = sum(character.isupper() for character in latin_letters)
    lowercase_count = sum(character.islower() for character in latin_letters)

    if punctuation / len(core) > 0.3:
        return True
    if letters >= 5 and latin_letters:
        uppercase_ratio = uppercase_count / len(latin_letters)
        vowel_ratio = (
            sum(character.lower() in "aeiou" for character in latin_letters) / len(latin_letters)
        )
        if uppercase_ratio >= 0.8:
            return True
        if len(latin_letters) >= 7 and vowel_ratio <= 0.2:
            return True
    if digits and letters and len(core) >= 6:
        return True
    if len(latin_letters) >= 3 and uppercase_count == len(latin_letters):
        return True
    if (
        len(latin_letters) >= 3
        and uppercase_count >= 2
        and lowercase_count >= 1
        and re.search(r"[A-Z]{2,}[a-z]|[a-z]+[A-Z]{2,}", core)
    ):
        return True
    if len(latin_letters) <= 4 and uppercase_count >= 2 and lowercase_count == 1:
        return True

    return False


def _compute_line_structure_signal(markdown_text: str) -> float:
    content_lines = _iter_content_lines(markdown_text)
    if not content_lines:
        return 0.0

    total_characters = 0
    coherent_characters = 0
    for line in content_lines:
        line_length = _compact_character_count(line)
        if line_length == 0:
            continue
        total_characters += line_length
        if _is_coherent_line(line, line_length):
            coherent_characters += line_length

    if total_characters == 0:
        return 0.0
    return coherent_characters / total_characters


def _is_coherent_line(line: str, line_length: int) -> bool:
    word_count = len(line.split())
    cjk_count = sum(_is_cjk_character(character) for character in line)
    sentence_like_end = line.endswith((".", "。", "!", "！", "?", "？", ":", "：", ";", "；"))

    return bool(
        line_length >= 45
        or word_count >= 8
        or cjk_count >= 15
        or (sentence_like_end and line_length >= 12)
    )


def _compute_table_fragment_signal(markdown_text: str) -> float:
    content_lines = _iter_content_lines(markdown_text)
    if not content_lines:
        return 0.0

    total_characters = 0
    fragmented_characters = 0
    for line in content_lines:
        line_length = _compact_character_count(line)
        if line_length == 0:
            continue
        total_characters += line_length
        if _looks_like_fragmented_table_line(line):
            fragmented_characters += line_length

    if total_characters == 0:
        return 0.0
    return fragmented_characters / total_characters


def _looks_like_fragmented_table_line(line: str) -> bool:
    if "|" in line:
        return True

    tokens = [token for token in line.split() if token]
    if len(tokens) < 4:
        return False

    numeric_tokens = sum(any(character.isdigit() for character in token) for token in tokens)
    numeric_ratio = numeric_tokens / len(tokens)
    average_token_length = sum(len(token) for token in tokens) / len(tokens)
    sentence_like_end = line.endswith((".", "。", "!", "！", "?", "？"))

    if (
        numeric_tokens >= 2
        and numeric_ratio >= 0.4
        and average_token_length <= 4.5
        and not sentence_like_end
    ):
        return True
    if numeric_ratio >= 0.6 and not sentence_like_end:
        return True

    return False


def _compute_content_trust_signals(markdown_text: str) -> dict[str, float]:
    return {
        "ocr_noise_ratio": _compute_ocr_noise_ratio(markdown_text),
        "line_structure_signal": _compute_line_structure_signal(markdown_text),
        "table_fragment_signal": _compute_table_fragment_signal(markdown_text),
    }


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


def _export_structured_document(document: Any) -> dict[str, Any]:
    export_to_dict = getattr(document, "export_to_dict", None)
    if callable(export_to_dict):
        return export_to_dict()

    model_dump = getattr(document, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")

    dict_method = getattr(document, "dict", None)
    if callable(dict_method):
        return dict_method()

    raise TypeError("Docling document does not expose a supported structured export method")


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
            main_text_stop=end,
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


def _serialize_page_quality(
    page_outputs: dict[int, PageArtifacts],
) -> dict[str, QualityReport]:
    return {
        str(page_no): page_output.quality
        for page_no, page_output in sorted(page_outputs.items())
    }


def _apply_artifact_authority(manifest: dict[str, Any]) -> dict[str, Any]:
    normalized_manifest = deepcopy(manifest)
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
) -> dict[str, Any]:
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


def _build_remediation_plan(
    ocr_engine: str,
    ocr_languages: list[str],
    primary_quality: dict[str, Any],
    *,
    force_full_page_ocr: bool = False,
) -> dict[str, Any] | None:
    if primary_quality.get("agent_ready"):
        return None
    return _build_ocr_remediation_config(
        ocr_engine=ocr_engine,
        ocr_languages=ocr_languages,
        force_full_page_ocr=force_full_page_ocr,
    )


def _build_ocr_remediation_config(
    ocr_engine: str,
    ocr_languages: list[str],
    *,
    force_full_page_ocr: bool = False,
) -> dict[str, Any] | None:
    if force_full_page_ocr:
        return None

    remediation_engine = "tesseract" if ocr_engine in {"auto", "ocrmac"} else ocr_engine
    remediation_languages = _normalize_engine_languages(remediation_engine, ocr_languages)
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


def _finalize_selected_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    finalized = _apply_artifact_authority(manifest)
    quality = finalized["quality"]

    if finalized.get("attempt") != "primary" and quality.get("agent_ready"):
        quality["status"] = "salvaged"
        if "ocr_remediation_selected" not in quality["reasons"]:
            quality["reasons"] = [*quality["reasons"], "ocr_remediation_selected"]

    return finalized


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
