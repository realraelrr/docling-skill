from pathlib import Path

import pytest

import docling_skill.core as core


def _quality(outputs: dict[str, object]) -> dict[str, object]:
    return outputs["manifest"]["quality"]  # type: ignore[index,return-value]


def test_quality_benchmark_keeps_markdown_note_low_risk(tmp_path: Path):
    input_path = tmp_path / "note.md"
    input_path.write_text("# Note\n\nDone\n", encoding="utf-8")

    outputs = core.convert_document_to_ingestion_outputs(
        input_path=input_path,
        output_dir=tmp_path / "out-md",
    )

    quality = _quality(outputs)
    assert quality["status"] == "good"
    assert quality["risk_level"] == "low"
    assert quality["warnings"] == []
    assert quality["signals"]["structure_survival"]["status"] == "pass"


def test_quality_benchmark_keeps_blank_image_high_risk(tmp_path: Path):
    pil_image = pytest.importorskip("PIL.Image")
    input_path = tmp_path / "blank.png"
    image = pil_image.new("RGB", (80, 80), color="white")
    image.save(input_path, format="PNG")

    outputs = core.convert_document_to_ingestion_outputs(
        input_path=input_path,
        output_dir=tmp_path / "out-image",
    )

    quality = _quality(outputs)
    assert quality["status"] == "failed_for_agent"
    assert quality["risk_level"] == "high"
    assert "low_text_content" in quality["reasons"]
    assert quality["signals"]["content_coverage"]["status"] == "fail"


def test_quality_benchmark_keeps_simple_pptx_low_risk(tmp_path: Path):
    pptx = pytest.importorskip("pptx")
    presentation = pptx.Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[1])
    slide.shapes.title.text = "Quarterly Plan"
    slide.placeholders[1].text = "This slide has enough body text for ingestion quality checks."

    input_path = tmp_path / "plan.pptx"
    presentation.save(input_path)

    outputs = core.convert_document_to_ingestion_outputs(
        input_path=input_path,
        output_dir=tmp_path / "out-pptx",
    )

    quality = _quality(outputs)
    assert quality["status"] == "good"
    assert quality["risk_level"] == "low"
    assert quality["warnings"] == []
    assert quality["signals"]["structure_survival"]["status"] == "pass"


def test_quality_benchmark_keeps_simple_xlsx_low_risk(tmp_path: Path):
    openpyxl = pytest.importorskip("openpyxl")
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Revenue"
    sheet.append(["Region", "Online", "Retail"])
    sheet.append(["North", 100, 80])
    sheet.append(["South", 120, 90])

    input_path = tmp_path / "revenue.xlsx"
    workbook.save(input_path)

    outputs = core.convert_document_to_ingestion_outputs(
        input_path=input_path,
        output_dir=tmp_path / "out-xlsx",
    )

    quality = _quality(outputs)
    assert quality["status"] == "good"
    assert quality["risk_level"] == "low"
    assert quality["warnings"] == []
    assert quality["signals"]["structure_survival"]["status"] == "pass"


def test_quality_benchmark_keeps_simple_csv_low_risk(tmp_path: Path):
    input_path = tmp_path / "revenue.csv"
    input_path.write_text(
        "Region,Online,Retail\nNorth,100,80\nSouth,120,90\n",
        encoding="utf-8",
    )

    outputs = core.convert_document_to_ingestion_outputs(
        input_path=input_path,
        output_dir=tmp_path / "out-csv",
    )

    quality = _quality(outputs)
    assert quality["status"] == "good"
    assert quality["risk_level"] == "low"
    assert quality["warnings"] == []
    assert quality["signals"]["structure_survival"]["status"] == "pass"
