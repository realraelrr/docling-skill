#!/usr/bin/env python3
"""Extract agent-friendly markdown and image sidecars from a PDF.

Usage: docling-skill <pdf_path> <output_dir>

Outputs:
- <stem>.md: Markdown with stable image placeholders like [[image:picture-0]]
- <stem>.images.json: Base64-encoded image sidecars keyed by placeholder/id
- <stem>.manifest.json: Document-level metadata for downstream consumers
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
    "convert_pdf_to_sidecar_outputs",
    "main",
]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf_path")
    parser.add_argument("output_dir", nargs="?", default="/tmp/docling-output")
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
        help="OCR languages. Repeat the flag or pass a comma-separated list.",
    )
    parser.add_argument(
        "--force-full-page-ocr",
        action="store_true",
        help="Force OCR over the entire page instead of hybrid extraction.",
    )
    parser.add_argument(
        "--no-ocr-remediation",
        action="store_true",
        help="Disable the full-page OCR retry used when the primary output fails agent-quality checks.",
    )
    return parser


def _print_conversion_summary(pdf_path: Path, outputs: dict[str, Any]) -> None:
    manifest = outputs["manifest"]
    markdown_text = outputs["markdown_text"]
    images = outputs["images"]

    print(f"Converted: {pdf_path.name} -> {outputs['markdown_path']}")
    print(f"Characters: {len(markdown_text)}")
    print(f"Images: {len(images)}")
    print(
        f"Quality: {manifest['quality']['status']} "
        f"(agent_ready={manifest['quality']['agent_ready']})"
    )
    print(f"Sidecars: {outputs['images_path'].name}, {outputs['manifest_path'].name}")
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

    pdf_path = Path(args.pdf_path).resolve()
    output_dir = Path(args.output_dir)

    outputs = convert_pdf_to_sidecar_outputs(
        pdf_path=pdf_path,
        output_dir=output_dir,
        ocr_engine=args.ocr_engine,
        ocr_languages=args.ocr_languages,
        force_full_page_ocr=args.force_full_page_ocr,
        ocr_remediation=not args.no_ocr_remediation,
    )
    _print_conversion_summary(pdf_path, outputs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
