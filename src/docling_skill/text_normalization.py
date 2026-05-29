"""Targeted cleanup for agent-facing Markdown text."""

from __future__ import annotations

import re
import unicodedata


CJK_SPACE_PATTERN = re.compile(r"(?<=[\u3400-\u9fff])[\t ]+(?=[\u3400-\u9fff])")


def _is_cjk_compatibility_character(character: str) -> bool:
    codepoint = ord(character)
    return (
        0x2E80 <= codepoint <= 0x2EFF
        or 0x2F00 <= codepoint <= 0x2FDF
        or 0xF900 <= codepoint <= 0xFAFF
    )


def _normalize_cjk_compatibility_characters(text: str) -> tuple[str, int]:
    replacements = 0
    normalized_characters: list[str] = []

    for character in text:
        if not _is_cjk_compatibility_character(character):
            normalized_characters.append(character)
            continue

        normalized = unicodedata.normalize("NFKC", character)
        if (
            len(normalized) == 1
            and normalized != character
            and "\u3400" <= normalized <= "\u9fff"
        ):
            normalized_characters.append(normalized)
            replacements += 1
        else:
            normalized_characters.append(character)

    return "".join(normalized_characters), replacements


def _merge_cjk_spacing(text: str) -> tuple[str, int]:
    merge_count = 0

    def replace_space(match: re.Match[str]) -> str:
        nonlocal merge_count
        merge_count += 1
        return ""

    return CJK_SPACE_PATTERN.sub(replace_space, text), merge_count


def normalize_agent_markdown(markdown_text: str) -> tuple[str, dict[str, int | bool]]:
    """Normalize only narrow CJK artifacts in Markdown consumed by agents."""
    in_fence = False
    fence_marker = ""
    normalized_lines: list[str] = []
    replacement_count = 0
    space_merge_count = 0

    for line in markdown_text.splitlines(keepends=True):
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
                fence_marker = ""
            normalized_lines.append(line)
            continue

        if in_fence:
            normalized_lines.append(line)
            continue

        normalized_line, line_replacements = _normalize_cjk_compatibility_characters(line)
        normalized_line, line_merges = _merge_cjk_spacing(normalized_line)
        replacement_count += line_replacements
        space_merge_count += line_merges
        normalized_lines.append(normalized_line)

    return "".join(normalized_lines), {
        "applied": replacement_count > 0 or space_merge_count > 0,
        "cjk_compatibility_replacement_count": replacement_count,
        "cjk_space_merge_count": space_merge_count,
    }
