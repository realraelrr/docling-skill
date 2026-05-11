"""Quality gates and content-trust helpers for ingestion outputs."""

from __future__ import annotations

import re
from typing import Any

from .constants import (
    IMAGE_TOKEN_PATTERN,
    MARKDOWN_PREFIX_PATTERN,
    MAX_OCR_NOISE_RATIO,
    MAX_TABLE_FRAGMENT_SIGNAL,
    MIN_AGENT_TEXT_CHARACTERS,
    MIN_LINE_STRUCTURE_SIGNAL,
    TOKEN_PATTERN,
)
from .models import ImageSidecar


def _compact_character_count(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def _assess_agent_quality(
    markdown_text: str,
    pictures: list[ImageSidecar],
    page_count: int,
    min_required_text: int | None = None,
    *,
    strip_image_tokens=None,
    compact_character_count=_compact_character_count,
    compute_content_trust_signals=None,
) -> dict[str, Any]:
    if strip_image_tokens is None:
        strip_image_tokens = _strip_image_tokens
    placeholder_count = len(IMAGE_TOKEN_PATTERN.findall(markdown_text))
    text_without_placeholders = strip_image_tokens(markdown_text)
    non_placeholder_characters = compact_character_count(text_without_placeholders)
    required_text = (
        min_required_text
        if min_required_text is not None
        else max(MIN_AGENT_TEXT_CHARACTERS, page_count * 20)
    )
    if compute_content_trust_signals is None:
        compute_content_trust_signals = _compute_content_trust_signals
    content_trust = compute_content_trust_signals(text_without_placeholders)

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
    *,
    strip_image_tokens=None,
    compact_character_count=_compact_character_count,
    compute_text_native_structure_signals=None,
    min_text_native_characters=None,
    has_text_native_body_survival=None,
    compute_content_trust_signals=None,
) -> dict[str, Any]:
    if strip_image_tokens is None:
        strip_image_tokens = _strip_image_tokens
    if has_text_native_body_survival is None:
        has_text_native_body_survival = _has_text_native_body_survival
    placeholder_count = len(IMAGE_TOKEN_PATTERN.findall(markdown_text))
    text_without_placeholders = strip_image_tokens(markdown_text)
    non_placeholder_characters = compact_character_count(text_without_placeholders)
    if compute_text_native_structure_signals is None:
        compute_text_native_structure_signals = _compute_text_native_structure_signals
    if min_text_native_characters is None:
        min_text_native_characters = _min_text_native_characters
    if compute_content_trust_signals is None:
        compute_content_trust_signals = _compute_content_trust_signals
    structure_signals = compute_text_native_structure_signals(
        text_without_placeholders,
        input_type=input_type,
    )

    reasons: list[str] = []
    if non_placeholder_characters < min_text_native_characters(
        input_type,
        structure_signals=structure_signals,
    ):
        reasons.append("low_text_content")
    if placeholder_count > 0 and non_placeholder_characters == 0:
        reasons.append("image_only_output")
    if (
        non_placeholder_characters
        >= min_text_native_characters(input_type, structure_signals=structure_signals)
        and not has_text_native_body_survival(input_type, structure_signals)
    ):
        reasons.append("missing_body_structure")

    status = "good" if not reasons else "failed_for_agent"

    return {
        "status": status,
        "agent_ready": status == "good",
        "reasons": reasons,
        "placeholder_count": placeholder_count,
        "non_placeholder_characters": non_placeholder_characters,
        "min_required_text_characters": min_text_native_characters(
            input_type,
            structure_signals=structure_signals,
        ),
        "picture_count": len(pictures),
        "content_trust": compute_content_trust_signals(text_without_placeholders),
    }


def _assess_spreadsheet_quality(
    markdown_text: str,
    pictures: list[ImageSidecar],
    structured_document: dict[str, Any],
    *,
    strip_image_tokens=None,
    compact_spreadsheet_markdown_character_count=None,
    has_spreadsheet_table_content=None,
    compute_content_trust_signals=None,
) -> dict[str, Any]:
    if strip_image_tokens is None:
        strip_image_tokens = _strip_image_tokens
    if compact_spreadsheet_markdown_character_count is None:
        compact_spreadsheet_markdown_character_count = (
            _compact_spreadsheet_markdown_character_count
        )
    placeholder_count = len(IMAGE_TOKEN_PATTERN.findall(markdown_text))
    text_without_placeholders = strip_image_tokens(markdown_text)
    non_placeholder_characters = compact_spreadsheet_markdown_character_count(
        text_without_placeholders
    )
    if has_spreadsheet_table_content is None:
        has_spreadsheet_table_content = _has_spreadsheet_table_content
    if compute_content_trust_signals is None:
        compute_content_trust_signals = _compute_content_trust_signals
    has_table_structure = has_spreadsheet_table_content(structured_document)

    reasons: list[str] = []
    if non_placeholder_characters == 0:
        reasons.append("low_text_content")
    if not has_table_structure:
        reasons.append("low_table_content")
    if placeholder_count > 0 and non_placeholder_characters == 0 and not has_table_structure:
        reasons.append("image_only_output")

    status = "good" if not reasons else "failed_for_agent"

    return {
        "status": status,
        "agent_ready": status == "good",
        "reasons": reasons,
        "placeholder_count": placeholder_count,
        "non_placeholder_characters": non_placeholder_characters,
        "min_required_text_characters": 0,
        "picture_count": len(pictures),
        "content_trust": compute_content_trust_signals(text_without_placeholders),
    }


def _compact_spreadsheet_markdown_character_count(markdown_text: str) -> int:
    semantic_text = re.sub(r"[|\-:+\s]", "", markdown_text)
    return len(semantic_text)


def _has_spreadsheet_table_content(
    structured_document: dict[str, Any],
    *,
    compact_character_count=_compact_character_count,
) -> bool:
    tables = structured_document.get("tables", [])
    for table in tables:
        if not isinstance(table, dict):
            continue
        data = table.get("data", {})
        if not isinstance(data, dict):
            continue
        for cell in data.get("table_cells", []):
            if isinstance(cell, dict) and compact_character_count(str(cell.get("text", ""))) > 0:
                return True
    return False


def _strip_image_tokens(markdown_text: str) -> str:
    return IMAGE_TOKEN_PATTERN.sub("", markdown_text)


def _min_text_native_characters(
    input_type: str,
    *,
    structure_signals: dict[str, int | bool] | None = None,
    min_concise_structured_body_characters=None,
) -> int:
    if min_concise_structured_body_characters is None:
        min_concise_structured_body_characters = _min_concise_structured_body_characters
    if input_type == "txt":
        return 3
    if (
        structure_signals
        and structure_signals["has_heading"]
        and (
            structure_signals["body_characters"] >= min_concise_structured_body_characters(input_type)
            or structure_signals["list_lexical_token_count"] >= 1
        )
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


def _strip_list_marker(line: str) -> str:
    return re.sub(r"^([-*+]\s+|\d+\.\s+)", "", line).strip()


def _compute_text_native_structure_signals(
    markdown_text: str,
    *,
    input_type: str,
    compact_character_count=_compact_character_count,
    count_lexical_tokens=None,
    strip_list_marker=None,
    min_text_native_body_characters=None,
    min_concise_structured_body_characters=None,
) -> dict[str, int | bool]:
    if count_lexical_tokens is None:
        count_lexical_tokens = _count_lexical_tokens
    if strip_list_marker is None:
        strip_list_marker = _strip_list_marker
    if min_text_native_body_characters is None:
        min_text_native_body_characters = _min_text_native_body_characters
    if min_concise_structured_body_characters is None:
        min_concise_structured_body_characters = _min_concise_structured_body_characters
    raw_lines = [line.rstrip() for line in markdown_text.splitlines()]
    content_lines = [line.strip() for line in raw_lines if line.strip()]
    heading_lines = [line for line in content_lines if re.match(r"^#{1,6}\s+\S", line)]
    list_lines = [line for line in content_lines if re.match(r"^([-*+]\s+|\d+\.\s+)", line)]
    body_lines = [
        line for line in content_lines if line not in heading_lines and line not in list_lines
    ]
    body_characters = sum(compact_character_count(line) for line in body_lines)
    body_lexical_token_count = count_lexical_tokens(body_lines)
    list_lexical_token_count = count_lexical_tokens(
        [strip_list_marker(line) for line in list_lines]
    )

    return {
        "has_heading": bool(heading_lines),
        "has_list_markers": bool(list_lines),
        "heading_count": len(heading_lines),
        "list_item_count": len(list_lines),
        "list_lexical_token_count": list_lexical_token_count,
        "body_line_count": len(body_lines),
        "body_characters": body_characters,
        "body_lexical_token_count": body_lexical_token_count,
        "paragraph_survival": bool(body_lines)
        and (
            body_characters >= min_text_native_body_characters(input_type)
            or (
                bool(heading_lines)
                and body_characters >= min_concise_structured_body_characters(input_type)
                and body_lexical_token_count >= 1
            )
        ),
        "list_survival": list_lexical_token_count >= 1,
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


def _iter_content_lines(
    markdown_text: str,
    *,
    normalize_analysis_line=_normalize_analysis_line,
) -> list[str]:
    return [
        normalized
        for raw_line in markdown_text.splitlines()
        if (normalized := normalize_analysis_line(raw_line))
    ]


def _is_cjk_character(character: str) -> bool:
    return "\u4e00" <= character <= "\u9fff"


def _compute_ocr_noise_ratio(
    markdown_text: str,
    *,
    is_suspicious_token=None,
) -> float:
    if is_suspicious_token is None:
        is_suspicious_token = _is_suspicious_token
    tokens = TOKEN_PATTERN.findall(markdown_text)
    analyzable_tokens = [token for token in tokens if re.search(r"[A-Za-z0-9\u4e00-\u9fff]", token)]
    if not analyzable_tokens:
        return 0.0

    suspicious_count = sum(1 for token in analyzable_tokens if is_suspicious_token(token))
    return suspicious_count / len(analyzable_tokens)


def _is_suspicious_token(
    token: str,
    *,
    is_cjk_character=_is_cjk_character,
) -> bool:
    core = token.strip(".,;:!?()[]{}<>\"'`|/\\+-=_~")
    if not core:
        return False

    letters = sum(character.isalpha() for character in core)
    digits = sum(character.isdigit() for character in core)
    cjk = sum(is_cjk_character(character) for character in core)
    punctuation = len(core) - letters - digits - cjk
    latin_letters = [
        character
        for character in core
        if character.isalpha() and not is_cjk_character(character)
    ]
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


def _compute_line_structure_signal(
    markdown_text: str,
    *,
    iter_content_lines=_iter_content_lines,
    compact_character_count=_compact_character_count,
    is_coherent_line=None,
) -> float:
    if is_coherent_line is None:
        is_coherent_line = _is_coherent_line
    content_lines = iter_content_lines(markdown_text)
    if not content_lines:
        return 0.0

    total_characters = 0
    coherent_characters = 0
    for line in content_lines:
        line_length = compact_character_count(line)
        if line_length == 0:
            continue
        total_characters += line_length
        if is_coherent_line(line, line_length):
            coherent_characters += line_length

    if total_characters == 0:
        return 0.0
    return coherent_characters / total_characters


def _is_coherent_line(
    line: str,
    line_length: int,
    *,
    is_cjk_character=_is_cjk_character,
) -> bool:
    word_count = len(line.split())
    cjk_count = sum(is_cjk_character(character) for character in line)
    sentence_like_end = line.endswith((".", "。", "!", "！", "?", "？", ":", "：", ";", "；"))

    return bool(
        line_length >= 45
        or word_count >= 8
        or cjk_count >= 15
        or (sentence_like_end and line_length >= 12)
    )


def _compute_table_fragment_signal(
    markdown_text: str,
    *,
    iter_content_lines=_iter_content_lines,
    compact_character_count=_compact_character_count,
    looks_like_fragmented_table_line=None,
) -> float:
    if looks_like_fragmented_table_line is None:
        looks_like_fragmented_table_line = _looks_like_fragmented_table_line
    content_lines = iter_content_lines(markdown_text)
    if not content_lines:
        return 0.0

    total_characters = 0
    fragmented_characters = 0
    for line in content_lines:
        line_length = compact_character_count(line)
        if line_length == 0:
            continue
        total_characters += line_length
        if looks_like_fragmented_table_line(line):
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


def _compute_content_trust_signals(
    markdown_text: str,
    *,
    compute_ocr_noise_ratio=_compute_ocr_noise_ratio,
    compute_line_structure_signal=_compute_line_structure_signal,
    compute_table_fragment_signal=_compute_table_fragment_signal,
) -> dict[str, float]:
    return {
        "ocr_noise_ratio": compute_ocr_noise_ratio(markdown_text),
        "line_structure_signal": compute_line_structure_signal(markdown_text),
        "table_fragment_signal": compute_table_fragment_signal(markdown_text),
    }
