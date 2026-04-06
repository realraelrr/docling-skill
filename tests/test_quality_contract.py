from docling_skill.core import (
    _assess_agent_quality,
    _compute_line_structure_signal,
    _compute_ocr_noise_ratio,
    _compute_table_fragment_signal,
)


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
