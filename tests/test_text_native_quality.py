from docling_skill.core import _assess_text_native_quality


def test_text_native_quality_keeps_docx_heading_and_paragraph_output_good():
    quality = _assess_text_native_quality(
        markdown_text="# Example Title\n\nThis docx paragraph survives as usable body text.\n",
        pictures=[],
        input_type="docx",
    )

    assert quality["status"] == "good"
    assert quality["agent_ready"] is True
    assert quality["reasons"] == []


def test_text_native_quality_keeps_html_heading_and_paragraph_output_good():
    quality = _assess_text_native_quality(
        markdown_text="# Example Title\n\nThis html paragraph survives with clear body structure.\n",
        pictures=[],
        input_type="html",
    )

    assert quality["status"] == "good"
    assert quality["agent_ready"] is True
    assert quality["reasons"] == []


def test_text_native_quality_keeps_clean_list_only_markdown_good():
    quality = _assess_text_native_quality(
        markdown_text="# Shopping List\n\n- Eggs\n- Milk\n- Bread\n",
        pictures=[],
        input_type="md",
    )

    assert quality["status"] == "good"
    assert quality["agent_ready"] is True
    assert quality["reasons"] == []


def test_text_native_quality_rejects_near_empty_text_native_output():
    quality = _assess_text_native_quality(
        markdown_text="OK",
        pictures=[],
        input_type="html",
    )

    assert quality["status"] == "failed_for_agent"
    assert quality["agent_ready"] is False
    assert "low_text_content" in quality["reasons"]


def test_text_native_quality_rejects_image_only_markdown():
    quality = _assess_text_native_quality(
        markdown_text="[[image:picture-p0-0]]",
        pictures=[{"id": "picture-p0-0"}],
        input_type="docx",
    )

    assert quality["status"] == "failed_for_agent"
    assert quality["agent_ready"] is False
    assert "image_only_output" in quality["reasons"]


def test_text_native_quality_keeps_txt_expectations_looser():
    quality = _assess_text_native_quality(
        markdown_text="Loose plain text survives.",
        pictures=[],
        input_type="txt",
    )

    assert quality["status"] == "good"
    assert quality["agent_ready"] is True
    assert quality["reasons"] == []
