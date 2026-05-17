"""Shared constants for local document ingestion outputs."""

from __future__ import annotations

import re
from pathlib import Path

from docling.datamodel.base_models import InputFormat

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
    ".xls": "xls",
    ".xlsx": "xlsx",
    ".xlsm": "xlsm",
    ".csv": "csv",
    ".html": "html",
    ".htm": "html",
    ".txt": "txt",
    ".md": "md",
}
TEXT_NATIVE_INPUT_TYPES = {"docx", "html", "txt", "md"}
TEXT_NATIVE_INPUT_FORMATS = {
    "docx": InputFormat.DOCX,
    "html": InputFormat.HTML,
    "txt": InputFormat.MD,
    "md": InputFormat.MD,
}
SPREADSHEET_INPUT_TYPES = {"xlsx", "csv", "xls"}
SPREADSHEET_INPUT_FORMATS = {
    "xlsx": InputFormat.XLSX,
    "csv": InputFormat.CSV,
}
