#!/usr/bin/env python3
"""Normalize a local document into workflow-ready agent ingestion artifacts.

Supported local inputs:
- pdf
- docx
- pptx
- xls
- xlsx
- csv
- html
- txt
- md
- png, jpg, jpeg, tif, tiff, bmp, webp

Outputs:
- source.md: Markdown with stable image placeholders like [[image:picture-p2-0]]
- source.manifest.json: Compact agent decision metadata
- source.evidence.json: On-demand structured evidence, quality signals, attempts, and image sidecars

Notes:
- OCR flags mainly affect PDF ingestion.
- PDF embedded images are supported; webpage image capture belongs to the fetcher/browser layer.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from .core import convert_document_to_ingestion_outputs, convert_pdf_to_sidecar_outputs

__all__ = [
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
        help=(
            "Local input artifact. Supported: pdf, docx, pptx, xls, xlsx, csv, "
            "html, txt, md, png, jpg, jpeg, tif, tiff, bmp, webp."
        ),
    )
    parser.add_argument(
        "output_dir",
        help="Explicit directory for source.md, source.manifest.json, and source.evidence.json.",
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
    parser.add_argument(
        "--pdf-audit",
        action="store_true",
        help="Record optional PDF audit intent for eligible native formats. Renderer support is not enabled by default.",
    )
    return parser


def _print_conversion_summary(input_path: Path, outputs: dict[str, Any]) -> None:
    manifest = outputs["manifest"]
    evidence = outputs["evidence"]
    decision = manifest["decision"]
    content_text = outputs["content_text"]

    print(f"Converted: {input_path.name} -> {outputs['content_path']}")
    print(f"Characters: {len(content_text)}")
    print(f"Images: {len(evidence['images'])}")
    print(f"Input type: {manifest['source']['input_type']}")
    print(
        f"Quality: {decision['status']} "
        f"(risk_level={decision['risk_level']}, "
        f"agent_ready={decision['agent_ready']})"
    )
    print(
        "Sidecars: "
        f"{outputs['manifest_path'].name}, "
        f"{outputs['evidence_path'].name}"
    )
    print(f"Read order: {', '.join(decision['read_order'])}")
    print(f"Evidence: {outputs['evidence_path'].name}")
    print(
        f"Selected attempt: {evidence['selected_attempt']} "
        f"(remediation_applied={evidence['ocr_remediation_applied']})"
    )
    preview = content_text[:500]
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
        pdf_audit=args.pdf_audit,
    )
    _print_conversion_summary(input_path, outputs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
