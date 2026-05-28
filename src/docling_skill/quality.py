"""Quality gates and content-trust helpers for ingestion outputs."""

from __future__ import annotations

from collections import Counter
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


QUALITY_GATE = "minimum_viability"
QUALITY_LIMITATIONS = [
    "Automated checks do not verify semantic fidelity.",
    "Automated checks do not prove complete source-to-markdown alignment.",
]
RISK_LEVELS = ("low", "medium", "high")
RISK_RANK = {level: rank for rank, level in enumerate(RISK_LEVELS)}
MIN_REPETITION_TOKENS = 20
MAX_REPETITIVE_TOKEN_RATIO = 0.5


def _compact_character_count(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def _unique(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return deduped


def _raise_quality_risk(quality: dict[str, Any], risk_level: str) -> None:
    current = quality.get("risk_level", "low")
    if RISK_RANK[risk_level] > RISK_RANK.get(current, 0):
        quality["risk_level"] = risk_level


def _add_quality_warning(
    quality: dict[str, Any],
    warning: str,
    *,
    min_risk: str = "medium",
) -> None:
    quality["warnings"] = _unique([*quality.get("warnings", []), warning])
    _raise_quality_risk(quality, min_risk)


def _ensure_quality_evidence_fields(quality: dict[str, Any]) -> dict[str, Any]:
    quality.setdefault("warnings", [])
    quality.setdefault("gate", QUALITY_GATE)
    quality.setdefault("limitations", list(QUALITY_LIMITATIONS))
    quality.setdefault("signals", {})
    quality.setdefault(
        "risk_level",
        "high"
        if quality.get("status") == "failed_for_agent"
        else ("medium" if quality["warnings"] else "low"),
    )
    return quality


def _finalize_quality_report(
    *,
    status: str,
    reasons: list[str],
    warnings: list[str],
    placeholder_count: int,
    non_placeholder_characters: int,
    min_required_text_characters: int,
    picture_count: int,
    content_trust: dict[str, float],
    signals: dict[str, Any],
) -> dict[str, Any]:
    quality = {
        "status": status,
        "agent_ready": status == "good",
        "reasons": _unique(reasons),
        "warnings": _unique(warnings),
        "placeholder_count": placeholder_count,
        "non_placeholder_characters": non_placeholder_characters,
        "min_required_text_characters": min_required_text_characters,
        "picture_count": picture_count,
        "content_trust": content_trust,
        "risk_level": "high" if status == "failed_for_agent" else ("medium" if warnings else "low"),
        "gate": QUALITY_GATE,
        "limitations": list(QUALITY_LIMITATIONS),
        "signals": signals,
    }
    return quality


def _signal_status(*, failed: bool = False, warned: bool = False) -> str:
    if failed:
        return "fail"
    if warned:
        return "warn"
    return "pass"


def _compute_repetition_signal(markdown_text: str) -> dict[str, Any]:
    tokens = [
        token.lower()
        for token in TOKEN_PATTERN.findall(markdown_text)
        if re.search(r"[A-Za-z0-9\u4e00-\u9fff]", token)
    ]
    if not tokens:
        return {
            "status": "pass",
            "token_count": 0,
            "top_token": None,
            "top_token_ratio": 0.0,
            "max_repetitive_token_ratio": MAX_REPETITIVE_TOKEN_RATIO,
        }

    top_token, top_count = Counter(tokens).most_common(1)[0]
    top_token_ratio = top_count / len(tokens)
    warned = (
        len(tokens) >= MIN_REPETITION_TOKENS
        and top_token_ratio >= MAX_REPETITIVE_TOKEN_RATIO
    )
    return {
        "status": "warn" if warned else "pass",
        "token_count": len(tokens),
        "top_token": top_token,
        "top_token_ratio": top_token_ratio,
        "max_repetitive_token_ratio": MAX_REPETITIVE_TOKEN_RATIO,
    }


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
    repetition_signal = _compute_repetition_signal(text_without_placeholders)

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
    warnings: list[str] = []
    if not reasons and repetition_signal["status"] == "warn":
        warnings.append("repetitive_text")

    status = "good" if not reasons else "failed_for_agent"
    signals = {
        "content_coverage": {
            "status": _signal_status(failed="low_text_content" in reasons),
            "non_placeholder_characters": non_placeholder_characters,
            "min_required_text_characters": required_text,
            "placeholder_count": placeholder_count,
            "picture_count": len(pictures),
        },
        "structure_survival": {
            "status": "pass",
            "line_structure_signal": content_trust["line_structure_signal"],
        },
        "ocr_noise": {
            "status": _signal_status(failed="high_ocr_noise" in reasons),
            "ocr_noise_ratio": content_trust["ocr_noise_ratio"],
            "max_ocr_noise_ratio": MAX_OCR_NOISE_RATIO,
        },
        "layout_fragmentation": {
            "status": _signal_status(failed="fragmented_layout" in reasons),
            "line_structure_signal": content_trust["line_structure_signal"],
            "min_line_structure_signal": MIN_LINE_STRUCTURE_SIGNAL,
            "table_fragment_signal": content_trust["table_fragment_signal"],
            "max_table_fragment_signal": MAX_TABLE_FRAGMENT_SIGNAL,
        },
        "repetition": repetition_signal,
    }

    return _finalize_quality_report(
        status=status,
        reasons=reasons,
        warnings=warnings,
        placeholder_count=placeholder_count,
        non_placeholder_characters=non_placeholder_characters,
        min_required_text_characters=required_text,
        picture_count=len(pictures),
        content_trust=content_trust,
        signals=signals,
    )


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
    content_trust = compute_content_trust_signals(text_without_placeholders)
    repetition_signal = _compute_repetition_signal(text_without_placeholders)
    structure_signals = compute_text_native_structure_signals(
        text_without_placeholders,
        input_type=input_type,
    )
    required_text = min_text_native_characters(
        input_type,
        structure_signals=structure_signals,
    )

    reasons: list[str] = []
    if non_placeholder_characters < required_text:
        reasons.append("low_text_content")
    if placeholder_count > 0 and non_placeholder_characters == 0:
        reasons.append("image_only_output")
    if (
        non_placeholder_characters >= required_text
        and not has_text_native_body_survival(input_type, structure_signals)
    ):
        reasons.append("missing_body_structure")
    warnings: list[str] = []
    if not reasons and repetition_signal["status"] == "warn":
        warnings.append("repetitive_text")

    status = "good" if not reasons else "failed_for_agent"
    signals = {
        "content_coverage": {
            "status": _signal_status(failed="low_text_content" in reasons),
            "non_placeholder_characters": non_placeholder_characters,
            "min_required_text_characters": required_text,
            "placeholder_count": placeholder_count,
            "picture_count": len(pictures),
        },
        "structure_survival": {
            "status": _signal_status(failed="missing_body_structure" in reasons),
            **structure_signals,
        },
        "ocr_noise": {
            "status": _signal_status(failed="high_ocr_noise" in reasons),
            "ocr_noise_ratio": content_trust["ocr_noise_ratio"],
            "max_ocr_noise_ratio": MAX_OCR_NOISE_RATIO,
        },
        "layout_fragmentation": {
            "status": "pass",
            "line_structure_signal": content_trust["line_structure_signal"],
            "table_fragment_signal": content_trust["table_fragment_signal"],
        },
        "repetition": repetition_signal,
    }

    return _finalize_quality_report(
        status=status,
        reasons=reasons,
        warnings=warnings,
        placeholder_count=placeholder_count,
        non_placeholder_characters=non_placeholder_characters,
        min_required_text_characters=required_text,
        picture_count=len(pictures),
        content_trust=content_trust,
        signals=signals,
    )


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
    content_trust = compute_content_trust_signals(text_without_placeholders)
    table_signals = _compute_spreadsheet_table_signals(structured_document)
    has_table_structure = has_spreadsheet_table_content(structured_document)

    reasons: list[str] = []
    if non_placeholder_characters == 0:
        reasons.append("low_text_content")
    if not has_table_structure:
        reasons.append("low_table_content")
    if placeholder_count > 0 and non_placeholder_characters == 0 and not has_table_structure:
        reasons.append("image_only_output")
    warnings: list[str] = []
    if not reasons and table_signals["non_empty_cell_count"] <= 2:
        warnings.append("thin_table_content")
    if (
        not reasons
        and table_signals["structured_text_characters"] >= 20
        and non_placeholder_characters
        < table_signals["structured_text_characters"] * 0.25
    ):
        warnings.append("markdown_structured_mismatch")

    status = "good" if not reasons else "failed_for_agent"
    signals = {
        "content_coverage": {
            "status": _signal_status(failed="low_text_content" in reasons),
            "non_placeholder_characters": non_placeholder_characters,
            "min_required_text_characters": 0,
            "placeholder_count": placeholder_count,
            "picture_count": len(pictures),
        },
        "structure_survival": {
            "status": _signal_status(
                failed="low_table_content" in reasons,
                warned="thin_table_content" in warnings,
            ),
            **table_signals,
        },
        "ocr_noise": {
            "status": "pass",
            "ocr_noise_ratio": content_trust["ocr_noise_ratio"],
            "max_ocr_noise_ratio": MAX_OCR_NOISE_RATIO,
        },
        "layout_fragmentation": {
            "status": "pass",
            "line_structure_signal": content_trust["line_structure_signal"],
            "table_fragment_signal": content_trust["table_fragment_signal"],
        },
    }

    return _finalize_quality_report(
        status=status,
        reasons=reasons,
        warnings=warnings,
        placeholder_count=placeholder_count,
        non_placeholder_characters=non_placeholder_characters,
        min_required_text_characters=0,
        picture_count=len(pictures),
        content_trust=content_trust,
        signals=signals,
    )


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


def _iter_spreadsheet_cells(structured_document: dict[str, Any]) -> list[dict[str, Any]]:
    cells: list[dict[str, Any]] = []
    for table in structured_document.get("tables", []):
        if not isinstance(table, dict):
            continue
        data = table.get("data", {})
        if not isinstance(data, dict):
            continue
        cells.extend(
            cell
            for cell in data.get("table_cells", [])
            if isinstance(cell, dict)
        )
    return cells


def _compute_spreadsheet_table_signals(
    structured_document: dict[str, Any],
    *,
    compact_character_count=_compact_character_count,
) -> dict[str, int]:
    tables = [
        table for table in structured_document.get("tables", [])
        if isinstance(table, dict)
    ]
    cells = _iter_spreadsheet_cells(structured_document)
    non_empty_cells = [
        cell
        for cell in cells
        if compact_character_count(str(cell.get("text", ""))) > 0
    ]
    return {
        "table_count": len(tables),
        "cell_count": len(cells),
        "non_empty_cell_count": len(non_empty_cells),
        "structured_text_characters": sum(
            compact_character_count(str(cell.get("text", "")))
            for cell in non_empty_cells
        ),
    }


def _apply_page_quality_risk(
    quality: dict[str, Any],
    page_quality: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    quality = _ensure_quality_evidence_fields(quality)
    if not page_quality:
        quality["signals"]["page_coverage"] = {
            "status": "pass",
            "page_count": 0,
            "failed_page_count": 0,
            "failed_page_ratio": 0.0,
            "failed_pages": [],
        }
        return quality

    page_count = len(page_quality)
    failed_pages = [
        page_no
        for page_no, page_report in sorted(page_quality.items())
        if not page_report.get("agent_ready", False)
    ]
    failed_page_ratio = len(failed_pages) / page_count
    fatal_page_failure = bool(
        failed_pages
        and (page_count == 1 or failed_pages[0] == 1 or failed_page_ratio >= 0.5)
    )
    page_signal = {
        "status": _signal_status(failed=fatal_page_failure, warned=bool(failed_pages)),
        "page_count": page_count,
        "failed_page_count": len(failed_pages),
        "failed_page_ratio": failed_page_ratio,
        "failed_pages": failed_pages,
    }
    quality["signals"]["page_coverage"] = page_signal

    if fatal_page_failure:
        quality["status"] = "failed_for_agent"
        quality["agent_ready"] = False
        quality["reasons"] = _unique([*quality.get("reasons", []), "page_quality_failed"])
        _raise_quality_risk(quality, "high")
    elif failed_pages:
        _add_quality_warning(quality, "page_quality_failed")

    return quality


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
