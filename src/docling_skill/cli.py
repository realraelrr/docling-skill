#!/usr/bin/env python3
"""Normalize a local document into workflow-ready agent ingestion artifacts.

Supported local inputs:
- pdf
- docx
- html
- txt
- md

Outputs:
- source.md: Markdown with stable image placeholders like [[image:picture-p2-0]]
- source.images.json: Image sidecars when extraction is available for the input
- source.manifest.json: Quality and routing metadata for downstream consumers
- source.meta.json: Lightweight ingestion metadata for downstream agents

Notes:
- OCR flags mainly affect PDF ingestion.
- PDF embedded images are supported; webpage image capture belongs to the fetcher/browser layer.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from .core import (
    AttemptArtifacts,
    PageArtifacts,
    _assess_agent_quality,
    _assess_page_qualities,
    _build_ocr_remediation_config,
    _build_ocr_options,
    _build_page_remediation_plan,
    _build_remediation_plan,
    _compute_line_structure_signal,
    _compute_ocr_noise_ratio,
    _compute_table_fragment_signal,
    _finalize_selected_manifest,
    _merge_page_attempts,
    _pick_better_attempt,
    convert_document_to_ingestion_outputs,
    convert_pdf_to_sidecar_outputs,
)

__all__ = [
    "AttemptArtifacts",
    "PageArtifacts",
    "_assess_agent_quality",
    "_assess_page_qualities",
    "_build_ocr_options",
    "_build_ocr_remediation_config",
    "_build_page_remediation_plan",
    "_build_remediation_plan",
    "_compute_ocr_noise_ratio",
    "_compute_line_structure_signal",
    "_compute_table_fragment_signal",
    "_finalize_selected_manifest",
    "_merge_page_attempts",
    "_pick_better_attempt",
    "convert_document_to_ingestion_outputs",
    "convert_pdf_to_sidecar_outputs",
    "main",
]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="docling-skill",
        description=__doc__,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "input_path",
        help="Local input artifact. Supported: pdf, docx, html, txt, md.",
    )
    parser.add_argument(
        "output_dir",
        nargs="?",
        default="/tmp/docling-output",
        help="Optional directory for source.md, source.images.json, source.manifest.json, and source.meta.json.",
    )
    parser.add_argument(
        "--ocr-engine",
        choices=["auto", "tesseract", "ocrmac", "rapidocr"],
        default="auto",
    )
    parser.add_argument(
        "--ocr-lang",
        action="append",
        dest="ocr_languages",
        default=[],
        help="OCR languages, mainly for PDF inputs. Repeat the flag or pass a comma-separated list.",
    )
    parser.add_argument(
        "--force-full-page-ocr",
        action="store_true",
        help="Force OCR over the entire page instead of hybrid extraction for PDF inputs.",
    )
    parser.add_argument(
        "--no-ocr-remediation",
        action="store_true",
        help="Disable the PDF full-page OCR retry used when the primary output fails agent-quality checks.",
    )
    return parser


def _print_conversion_summary(input_path: Path, outputs: dict[str, Any]) -> None:
    manifest = outputs["manifest"]
    meta = outputs["meta"]
    markdown_text = outputs["markdown_text"]
    images = outputs["images"]

    print(f"Converted: {input_path.name} -> {outputs['markdown_path']}")
    print(f"Characters: {len(markdown_text)}")
    print(f"Images: {len(images)}")
    print(f"Input type: {meta['input_type']}")
    print(
        f"Quality: {manifest['quality']['status']} "
        f"(agent_ready={manifest['quality']['agent_ready']})"
    )
    print(
        "Sidecars: "
        f"{outputs['images_path'].name}, "
        f"{outputs['manifest_path'].name}, "
        f"{outputs['meta_path'].name}"
    )
    print(
        f"Selected attempt: {manifest['selected_attempt']} "
        f"(remediation_applied={manifest['ocr_remediation_applied']})"
    )
    preview = markdown_text[:500]
    print(f"\n=== Preview (first 500 chars) ===\n{preview}...")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    cli_args = argv if argv is not None else sys.argv[1:]
    args = parser.parse_args(cli_args)

    input_path = Path(args.input_path).resolve()
    output_dir = Path(args.output_dir)

    outputs = convert_document_to_ingestion_outputs(
        input_path=input_path,
        output_dir=output_dir,
        ocr_engine=args.ocr_engine,
        ocr_languages=args.ocr_languages,
        force_full_page_ocr=args.force_full_page_ocr,
        ocr_remediation=not args.no_ocr_remediation,
    )
    _print_conversion_summary(input_path, outputs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
