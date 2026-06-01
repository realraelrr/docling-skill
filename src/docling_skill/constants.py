"""Shared constants for local document ingestion outputs."""

from __future__ import annotations

import re
from pathlib import Path

from docling.datamodel.base_models import InputFormat

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_VERSION = "2.0"
PRODUCER_NAME = "docling-skill"
PRODUCER_VERSION = "2.0.0"
IMAGE_PLACEHOLDER = "<!-- image -->"
IMAGE_TOKEN_PATTERN = re.compile(r"\[\[image:[^\]]+\]\]")
MARKDOWN_PREFIX_PATTERN = re.compile(r"^(#{1,6}\s+|[-*+]\s+|\d+\.\s+)")
TOKEN_PATTERN = re.compile(r"[^\s]+")
SOURCE_MARKDOWN_NAME = "source.md"
SOURCE_EVIDENCE_NAME = "source.evidence.json"
SOURCE_MANIFEST_NAME = "source.manifest.json"
STALE_SOURCE_SIDECAR_NAMES = (
    "source.docling.json",
    "source.images.json",
    "source.meta.json",
)
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
    ".xls": "xls",
    ".xlsx": "xlsx",
    ".xlsm": "xlsm",
    ".csv": "csv",
    ".html": "html",
    ".htm": "html",
    ".txt": "txt",
    ".md": "md",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".tif": "image",
    ".tiff": "image",
    ".bmp": "image",
    ".webp": "image",
}
TEXT_NATIVE_INPUT_TYPES = {"docx", "html", "txt", "md"}
TEXT_NATIVE_INPUT_FORMATS = {
    "docx": InputFormat.DOCX,
    "html": InputFormat.HTML,
    "txt": InputFormat.MD,
    "md": InputFormat.MD,
}
PRESENTATION_INPUT_TYPES = {"pptx"}
PRESENTATION_INPUT_FORMATS = {
    "pptx": InputFormat.PPTX,
}
IMAGE_INPUT_TYPES = {"image"}
IMAGE_INPUT_FORMATS = {
    "image": InputFormat.IMAGE,
}
SPREADSHEET_INPUT_TYPES = {"xlsx", "csv", "xls"}
SPREADSHEET_INPUT_FORMATS = {
    "xlsx": InputFormat.XLSX,
    "csv": InputFormat.CSV,
}
