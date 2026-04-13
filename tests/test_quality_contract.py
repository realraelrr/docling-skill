import json

from docling_skill.core import (
    _assess_agent_quality,
    _assess_text_native_quality,
    _compute_line_structure_signal,
    _compute_ocr_noise_ratio,
    _compute_table_fragment_signal,
    _export_structured_document,
    build_source_meta,
)


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
