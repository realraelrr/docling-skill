import json

from docling_skill.core import (
    build_source_meta,
)
from docling_skill.artifacts import _export_structured_document
from docling_skill.quality import (
    _assess_agent_quality,
    _assess_spreadsheet_quality,
    _assess_text_native_quality,
    _compute_text_integrity_signal,
    _compute_line_structure_signal,
    _compute_ocr_noise_ratio,
    _compute_table_fragment_signal,
)
from docling_skill.spreadsheet import _extract_spreadsheet_metadata


def test_export_structured_document_prefers_export_to_dict():
    class FakeDocument:
        def export_to_dict(self) -> dict[str, object]:
            return {
                "schema_name": "DoclingDocument",
                "body": "structured payload",
            }

        def model_dump(self) -> dict[str, object]:
            raise AssertionError("export_to_dict should be preferred when available")

    structured = _export_structured_document(FakeDocument())

    assert structured == {
        "schema_name": "DoclingDocument",
        "body": "structured payload",
    }


def test_compute_ocr_noise_ratio_detects_gibberish_tokens():
    markdown_text = """
    ## D JEEROSEMITRGT IL: KWAI
    e 0867): HRSA. WEA Wry setHBE—_AOe-
    BAe Sea rw HATE TMERNIATTS
    """

    noise_ratio = _compute_ocr_noise_ratio(markdown_text)

    assert noise_ratio > 0.25


def test_compute_line_structure_signal_rewards_natural_prose():
    markdown_text = """
    Large language models have changed how developers explore and modify code.
    This document explains the workflow, the major tradeoffs, and the reasons
    why some pipelines prefer conservative retries over aggressive rewrites.
    """

    line_signal = _compute_line_structure_signal(markdown_text)

    assert line_signal > 0.6


def test_compute_table_fragment_signal_detects_fragmented_rows():
    markdown_text = """
    Model     Acc   Prec   Rec   F1
    A12       91.2  88.4   87.9  88.1
    B07       90.8  87.5   88.0  87.7
    C55       89.1  85.0   84.8  84.9
    """

    table_signal = _compute_table_fragment_signal(markdown_text)

    assert table_signal > 0.35


def test_assess_agent_quality_flags_image_only_output():
    quality = _assess_agent_quality(
        markdown_text="[[image:picture-0]]\n\n[[image:picture-1]]\n",
        pictures=[{"id": "picture-0"}, {"id": "picture-1"}],
        page_count=2,
    )

    assert quality["status"] == "failed_for_agent"
    assert quality["agent_ready"] is False
    assert "low_text_content" in quality["reasons"]


def test_good_quality_report_includes_risk_evidence_model():
    quality = _assess_agent_quality(
        markdown_text="This paragraph has enough ordinary prose for the minimum viability gate. "
        "It is usable as agent input, but the automated gate does not prove semantic fidelity.",
        pictures=[],
        page_count=1,
    )

    assert quality["status"] == "good"
    assert quality["agent_ready"] is True
    assert quality["risk_level"] == "low"
    assert quality["warnings"] == []
    assert quality["gate"] == "minimum_viability"
    assert "semantic fidelity" in " ".join(quality["limitations"])
    assert {
        "content_coverage",
        "structure_survival",
        "ocr_noise",
        "layout_fragmentation",
    }.issubset(quality["signals"])


def test_assess_agent_quality_warns_on_repetitive_text_without_hard_failure():
    quality = _assess_agent_quality(
        markdown_text="foo " * 40,
        pictures=[],
        page_count=1,
    )

    assert quality["status"] == "good"
    assert quality["agent_ready"] is True
    assert quality["risk_level"] == "medium"
    assert "repetitive_text" in quality["warnings"]
    assert quality["signals"]["repetition"]["status"] == "warn"


def test_compute_text_integrity_signal_counts_replacement_compatibility_and_formulas():
    signal = _compute_text_integrity_signal(
        "周志华老师�。\n\n仍有⽠字。\n\n<!-- formula-not-decoded -->"
    )

    assert signal["replacement_character_count"] == 1
    assert signal["remaining_cjk_compatibility_count"] == 1
    assert signal["formula_not_decoded_count"] == 1


def test_assess_agent_quality_warns_on_formula_and_small_replacement_noise():
    quality = _assess_agent_quality(
        markdown_text=(
            "这是一段足够长的中文正文，用来模拟转换后的内容可以作为默认输入。"
            "它包含少量替换字符�，还包含公式占位。"
            "后续还有多段自然语言内容，用来确保最低文本覆盖门禁不会把这个样本误判为空。"
            "这些内容本身是可读的，只是需要提示人工或 agent 注意部分公式和个别坏字符。\n\n"
            "<!-- formula-not-decoded -->"
        ),
        pictures=[],
        page_count=1,
    )

    assert quality["status"] == "good"
    assert quality["agent_ready"] is True
    assert quality["risk_level"] == "medium"
    assert "replacement_characters" in quality["warnings"]
    assert "formula_not_decoded" in quality["warnings"]
    assert quality["signals"]["text_integrity"]["replacement_character_count"] == 1
    assert quality["signals"]["text_integrity"]["formula_not_decoded_count"] == 1


def test_assess_text_native_quality_rejects_formula_only_markdown():
    quality = _assess_text_native_quality(
        markdown_text="<!-- formula-not-decoded -->",
        pictures=[],
        input_type="md",
    )

    assert quality["status"] == "failed_for_agent"
    assert quality["agent_ready"] is False
    assert quality["risk_level"] == "high"
    assert "low_text_content" in quality["reasons"]
    assert "formula_not_decoded" in quality["warnings"]
    assert quality["signals"]["text_integrity"]["formula_not_decoded_count"] == 1


def test_assess_agent_quality_keeps_tiny_replacement_noise_as_signal_only():
    quality = _assess_agent_quality(
        markdown_text=("这是一段稳定的中文正文，用于模拟较长的可读转换结果。" * 200) + "�",
        pictures=[],
        page_count=1,
    )

    assert quality["status"] == "good"
    assert quality["agent_ready"] is True
    assert quality["risk_level"] == "low"
    assert "replacement_characters" not in quality["warnings"]
    assert quality["signals"]["text_integrity"]["replacement_character_count"] == 1


def test_assess_agent_quality_fails_on_excessive_replacement_characters():
    quality = _assess_agent_quality(
        markdown_text=("自然语言正文" * 30) + ("�" * 60),
        pictures=[],
        page_count=1,
    )

    assert quality["status"] == "failed_for_agent"
    assert quality["agent_ready"] is False
    assert quality["risk_level"] == "high"
    assert "excessive_replacement_characters" in quality["reasons"]


def test_assess_text_native_quality_accepts_short_nonempty_markdown():
    quality = _assess_text_native_quality(
        markdown_text="Short paragraph.",
        pictures=[],
        input_type="md",
    )

    assert quality["status"] == "good"
    assert quality["agent_ready"] is True
    assert quality["reasons"] == []


def test_assess_text_native_quality_rejects_heading_only_docx_output():
    quality = _assess_text_native_quality(
        markdown_text="# Example Title",
        pictures=[],
        input_type="docx",
    )

    assert quality["status"] == "failed_for_agent"
    assert quality["agent_ready"] is False
    assert "missing_body_structure" in quality["reasons"]


def test_assess_spreadsheet_quality_rejects_structured_table_without_markdown_preview():
    structured_document = {
        "tables": [
            {
                "data": {
                    "table_cells": [
                        {
                            "text": "Revenue",
                            "row_span": 1,
                            "col_span": 1,
                        }
                    ]
                }
            }
        ]
    }

    quality = _assess_spreadsheet_quality(
        markdown_text="",
        pictures=[],
        structured_document=structured_document,
    )

    assert quality["status"] == "failed_for_agent"
    assert quality["agent_ready"] is False
    assert "low_text_content" in quality["reasons"]


def test_assess_spreadsheet_quality_rejects_empty_table_structure():
    quality = _assess_spreadsheet_quality(
        markdown_text="",
        pictures=[],
        structured_document={"tables": [{"data": {"table_cells": []}}]},
    )

    assert quality["status"] == "failed_for_agent"
    assert quality["agent_ready"] is False
    assert "low_table_content" in quality["reasons"]


def test_assess_spreadsheet_quality_rejects_delimiter_only_csv_preview():
    quality = _assess_spreadsheet_quality(
        markdown_text=",\n,\n",
        pictures=[],
        structured_document={
            "tables": [
                {
                    "data": {
                        "table_cells": [
                            {"text": ""},
                            {"text": ""},
                        ]
                    }
                }
            ]
        },
    )

    assert quality["status"] == "failed_for_agent"
    assert quality["agent_ready"] is False
    assert "low_table_content" in quality["reasons"]


def test_assess_spreadsheet_quality_warns_on_single_cell_table():
    quality = _assess_spreadsheet_quality(
        markdown_text="Revenue",
        pictures=[],
        structured_document={
            "tables": [
                {
                    "data": {
                        "table_cells": [
                            {"text": "Revenue"},
                        ]
                    }
                }
            ]
        },
    )

    assert quality["status"] == "good"
    assert quality["agent_ready"] is True
    assert quality["risk_level"] == "medium"
    assert "thin_table_content" in quality["warnings"]
    assert quality["signals"]["structure_survival"]["non_empty_cell_count"] == 1


def test_extract_spreadsheet_metadata_counts_sheets_tables_and_merged_cells():
    structured_document = {
        "groups": [
            {"name": "sheet: Revenue"},
            {"name": "sheet: Nested"},
        ],
        "tables": [
            {
                "data": {
                    "table_cells": [
                        {"text": "FY2026 Revenue Plan", "row_span": 1, "col_span": 4},
                        {"text": "Region", "row_span": 2, "col_span": 1},
                        {"text": "North", "row_span": 1, "col_span": 1},
                    ]
                }
            },
            {
                "data": {
                    "table_cells": [
                        {"text": "Department", "row_span": 1, "col_span": 1},
                    ]
                }
            },
        ],
    }

    metadata = _extract_spreadsheet_metadata(structured_document)

    assert metadata == {
        "sheet_count": 2,
        "table_count": 2,
        "merged_cell_count": 2,
        "has_merged_cells": True,
        "has_multi_sheet": True,
    }


def test_extract_spreadsheet_metadata_only_includes_normalized_from_when_present():
    structured_document = {
        "pages": {"1": {}},
        "tables": [
            {
                "data": {
                    "table_cells": [
                        {"text": "Region", "row_span": 1, "col_span": 1},
                    ]
                }
            }
        ],
    }

    xlsx_metadata = _extract_spreadsheet_metadata(
        structured_document,
        source_format="xlsx",
    )
    xls_metadata = _extract_spreadsheet_metadata(
        structured_document,
        source_format="xls",
        normalized_from="xls",
    )

    assert xlsx_metadata["source_format"] == "xlsx"
    assert "normalized_from" not in xlsx_metadata
    assert xls_metadata["source_format"] == "xls"
    assert xls_metadata["normalized_from"] == "xls"


def test_build_source_meta_limits_fields_to_ingestion_metadata():
    manifest = {
        "pipeline_family": "simple",
        "quality": {
            "status": "salvaged",
            "reasons": ["ocr_remediation_selected"],
        }
    }

    meta = build_source_meta(
        input_path="book2-comparing.pdf",
        manifest=manifest,
        markdown_text="# Title\n\nContent body.\n",
        job_id="kb-20260411-001",
        source_title="Claude Code vs Codex Harness 设计哲学 — 殊途同归，还是各表一枝",
    )

    assert json.loads(json.dumps(meta, ensure_ascii=False)) == {
        "job_id": "kb-20260411-001",
        "input_type": "pdf",
        "source_title": "Claude Code vs Codex Harness 设计哲学 — 殊途同归，还是各表一枝",
        "source_url": None,
        "source_attachment": "book2-comparing.pdf",
        "author": None,
        "published_at": None,
        "extractor": "docling",
        "pipeline_family": "simple",
        "quality_status": "salvaged",
        "quality_reasons": ["ocr_remediation_selected"],
        "char_count": len("# Title\n\nContent body.\n"),
    }
