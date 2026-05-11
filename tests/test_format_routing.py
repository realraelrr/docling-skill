import base64
import json
import zlib
from pathlib import Path

import pytest
from docling.datamodel.base_models import ConversionStatus, InputFormat

import docling_skill.core as core


def _fake_attempt(input_path: Path, *, input_type: str, pipeline_family: str) -> core.AttemptArtifacts:
    return core.AttemptArtifacts(
        markdown_text="# Title\n\nBody text for ingestion.\n",
        images=[],
        page_outputs={},
        structured_document={
            "schema_name": "DoclingDocument",
            "name": input_path.name,
            "input_type": input_type,
        },
        manifest={
            "source_file": str(input_path),
            "attempt": "primary",
            "status": "success",
            "page_count": 1,
            "image_count": 0,
            "text_characters": 32,
            "document_markdown": "source.md",
            "images_json": "source.images.json",
            "input_type": input_type,
            "pipeline_family": pipeline_family,
            "quality": {
                "status": "good",
                "agent_ready": True,
                "reasons": [],
            },
            "page_quality": {},
        },
    )


def _assert_source_sidecar_contract(
    outputs: dict[str, object],
    *,
    expected_input_type: str,
    expected_pipeline_family: str,
):
    markdown_path = outputs["markdown_path"]
    images_path = outputs["images_path"]
    docling_json_path = outputs["docling_json_path"]
    manifest_path = outputs["manifest_path"]
    meta_path = outputs["meta_path"]

    assert markdown_path.name == "source.md"
    assert images_path.name == "source.images.json"
    assert docling_json_path.name == "source.docling.json"
    assert manifest_path.name == "source.manifest.json"
    assert meta_path.name == "source.meta.json"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["document_markdown"] == "source.md"
    assert manifest["images_json"] == "source.images.json"
    assert manifest["preferred_agent_artifact"] == "source.md"
    assert manifest["authoritative_artifact"] == "source.docling.json"
    assert manifest["available_artifacts"] == [
        "source.md",
        "source.docling.json",
        "source.images.json",
    ]
    assert manifest["input_type"] == expected_input_type
    assert manifest["pipeline_family"] == expected_pipeline_family
    assert manifest["quality"]["status"] == "good"
    assert manifest["quality"]["agent_ready"] is True

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["input_type"] == expected_input_type
    assert meta["pipeline_family"] == expected_pipeline_family
    assert meta["quality_status"] == "good"

    images = json.loads(images_path.read_text(encoding="utf-8"))
    assert images == []

    docling_document = json.loads(docling_json_path.read_text(encoding="utf-8"))
    assert docling_document == outputs["docling_document"]
    assert docling_document["schema_name"] == "DoclingDocument"


def _docling_json_text_values(docling_document: object) -> set[str]:
    values: set[str] = set()

    def collect(value: object) -> None:
        if isinstance(value, dict):
            text = value.get("text")
            if isinstance(text, str):
                values.add(text)
            for nested in value.values():
                collect(nested)
        elif isinstance(value, list):
            for nested in value:
                collect(nested)

    collect(docling_document)
    return values


@pytest.mark.parametrize(
    ("filename", "expected_type"),
    [
        ("sample.pdf", "pdf"),
        ("sample.docx", "docx"),
        ("sample.xls", "xls"),
        ("sample.xlsx", "xlsx"),
        ("sample.xlsm", "xlsm"),
        ("sample.csv", "csv"),
        ("sample.html", "html"),
        ("sample.txt", "txt"),
        ("sample.md", "md"),
    ],
)
def test_detect_input_type_normalizes_phase_one_formats(filename: str, expected_type: str):
    assert core.detect_input_type(Path(filename)) == expected_type


@pytest.mark.parametrize(
    ("suffix", "expected_type"),
    [
        (".docx", "docx"),
        (".html", "html"),
        (".txt", "txt"),
        (".md", "md"),
    ],
)
def test_convert_document_routes_text_native_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    suffix: str,
    expected_type: str,
):
    input_path = tmp_path / f"example{suffix}"
    output_dir = tmp_path / f"out-{expected_type}"
    calls: list[tuple[str, str]] = []

    def fake_text_native_converter(path: Path, *, input_type: str) -> tuple[core.AttemptArtifacts, list[dict[str, object]]]:
        calls.append((path.suffix, input_type))
        attempt = _fake_attempt(
            path,
            input_type=input_type,
            pipeline_family="simple",
        )
        return attempt, [attempt.manifest]

    def fail_pdf_converter(*args, **kwargs):
        raise AssertionError("PDF conversion path should not be used for text-native inputs")

    monkeypatch.setattr(core, "_convert_text_native_input", fake_text_native_converter, raising=False)
    monkeypatch.setattr(core, "_convert_pdf_input", fail_pdf_converter, raising=False)

    outputs = core.convert_document_to_ingestion_outputs(
        input_path=input_path,
        output_dir=output_dir,
    )

    assert calls == [(suffix, expected_type)]
    assert outputs["manifest"]["input_type"] == expected_type
    assert outputs["manifest"]["pipeline_family"] == "simple"
    assert outputs["meta"]["input_type"] == expected_type
    assert outputs["meta"]["pipeline_family"] == "simple"


def test_convert_document_routes_pdf_inputs_to_pdf_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    input_path = tmp_path / "example.pdf"
    output_dir = tmp_path / "out-pdf"
    calls: list[str] = []

    def fake_pdf_converter(
        path: Path,
        *,
        ocr_engine: str,
        ocr_languages: list[str],
        force_full_page_ocr: bool,
        ocr_remediation: bool,
    ) -> tuple[core.AttemptArtifacts, list[dict[str, object]]]:
        calls.append(path.suffix)
        attempt = _fake_attempt(
            path,
            input_type="pdf",
            pipeline_family="standard_pdf",
        )
        return attempt, [attempt.manifest]

    def fail_text_converter(*args, **kwargs):
        raise AssertionError("Text-native conversion path should not be used for PDF inputs")

    monkeypatch.setattr(core, "_convert_pdf_input", fake_pdf_converter, raising=False)
    monkeypatch.setattr(core, "_convert_text_native_input", fail_text_converter, raising=False)

    outputs = core.convert_document_to_ingestion_outputs(
        input_path=input_path,
        output_dir=output_dir,
    )

    assert calls == [".pdf"]
    assert outputs["manifest"]["input_type"] == "pdf"
    assert outputs["manifest"]["pipeline_family"] == "standard_pdf"
    assert outputs["meta"]["input_type"] == "pdf"
    assert outputs["meta"]["pipeline_family"] == "standard_pdf"


@pytest.mark.parametrize(
    ("suffix", "expected_type"),
    [
        (".xlsx", "xlsx"),
        (".csv", "csv"),
        (".xls", "xls"),
    ],
)
def test_convert_document_routes_supported_spreadsheet_inputs_to_spreadsheet_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    suffix: str,
    expected_type: str,
):
    input_path = tmp_path / f"example{suffix}"
    output_dir = tmp_path / f"out-{expected_type}"
    calls: list[tuple[str, str]] = []

    def fake_spreadsheet_converter(path: Path, *, input_type: str) -> tuple[core.AttemptArtifacts, list[dict[str, object]]]:
        calls.append((path.suffix, input_type))
        attempt = _fake_attempt(
            path,
            input_type=input_type,
            pipeline_family="spreadsheet",
        )
        attempt.manifest["spreadsheet"] = {
            "sheet_count": 1,
            "table_count": 1,
            "merged_cell_count": 0,
            "has_merged_cells": False,
            "has_multi_sheet": False,
        }
        return attempt, [attempt.manifest]

    def fail_pdf_converter(*args, **kwargs):
        raise AssertionError("PDF conversion path should not be used for spreadsheet inputs")

    def fail_text_converter(*args, **kwargs):
        raise AssertionError("Text-native conversion path should not be used for spreadsheet inputs")

    monkeypatch.setattr(core, "_convert_spreadsheet_input", fake_spreadsheet_converter, raising=False)
    monkeypatch.setattr(core, "_convert_pdf_input", fail_pdf_converter, raising=False)
    monkeypatch.setattr(core, "_convert_text_native_input", fail_text_converter, raising=False)

    outputs = core.convert_document_to_ingestion_outputs(
        input_path=input_path,
        output_dir=output_dir,
    )

    assert calls == [(suffix, expected_type)]
    assert outputs["manifest"]["input_type"] == expected_type
    assert outputs["manifest"]["pipeline_family"] == "spreadsheet"
    assert outputs["manifest"]["spreadsheet"]["table_count"] == 1
    assert outputs["meta"]["input_type"] == expected_type
    assert outputs["meta"]["pipeline_family"] == "spreadsheet"


def test_convert_document_rejects_deferred_input_types(tmp_path: Path):
    with pytest.raises(NotImplementedError, match=r"\.pptx"):
        core.convert_document_to_ingestion_outputs(
            input_path=tmp_path / "slides.pptx",
            output_dir=tmp_path / "out-pptx",
        )


def test_convert_document_rejects_xlsm_with_manual_preprocess_guidance(tmp_path: Path):
    with pytest.raises(NotImplementedError, match=r"Save as \.xlsx or \.csv"):
        core.convert_document_to_ingestion_outputs(
            input_path=tmp_path / "macro.xlsm",
            output_dir=tmp_path / "out-xlsm",
        )


@pytest.mark.parametrize(
    ("filename", "content", "expected_type", "expected_snippet"),
    [
        (
            "sample.md",
            "# Example Title\n\nThis markdown body should survive docling conversion.\n",
            "md",
            "markdown body should survive",
        ),
        (
            "sample.html",
            "<html><body><h1>Example Title</h1><p>This html body should survive docling conversion.</p></body></html>",
            "html",
            "html body should survive",
        ),
    ],
)
def test_convert_document_smoke_converts_real_text_native_files(
    tmp_path: Path,
    filename: str,
    content: str,
    expected_type: str,
    expected_snippet: str,
):
    input_path = tmp_path / filename
    input_path.write_text(content, encoding="utf-8")

    outputs = core.convert_document_to_ingestion_outputs(
        input_path=input_path,
        output_dir=tmp_path / f"out-{expected_type}",
    )

    _assert_source_sidecar_contract(
        outputs,
        expected_input_type=expected_type,
        expected_pipeline_family="simple",
    )
    assert "Example Title" in outputs["markdown_text"]
    assert expected_snippet in outputs["markdown_text"].lower()
    assert outputs["manifest"]["quality"]["reasons"] == []


def test_convert_document_smoke_converts_real_docx_file(tmp_path: Path):
    docx = pytest.importorskip("docx")
    document = docx.Document()
    document.add_heading("Example Title", level=1)
    document.add_paragraph("This docx body should survive docling conversion.")

    input_path = tmp_path / "sample.docx"
    document.save(input_path)

    outputs = core.convert_document_to_ingestion_outputs(
        input_path=input_path,
        output_dir=tmp_path / "out-docx",
    )

    _assert_source_sidecar_contract(
        outputs,
        expected_input_type="docx",
        expected_pipeline_family="simple",
    )
    assert "Example Title" in outputs["markdown_text"]
    assert "docx body should survive" in outputs["markdown_text"].lower()
    assert outputs["manifest"]["quality"]["reasons"] == []


def test_convert_document_smoke_converts_real_xlsx_file_with_merged_cells(tmp_path: Path):
    openpyxl = pytest.importorskip("openpyxl")
    workbook = openpyxl.Workbook()
    revenue_sheet = workbook.active
    revenue_sheet.title = "Revenue"
    revenue_sheet.merge_cells("A1:D1")
    revenue_sheet["A1"] = "FY2026 Revenue Plan"
    revenue_sheet.merge_cells("A2:A3")
    revenue_sheet["A2"] = "Region"
    revenue_sheet.merge_cells("B2:C2")
    revenue_sheet["B2"] = "Q1"
    revenue_sheet["D2"] = "Q2"
    revenue_sheet["B3"] = "Online"
    revenue_sheet["C3"] = "Retail"
    revenue_sheet["D3"] = "Total"
    revenue_sheet.append(["North", 100, 80, 210])
    revenue_sheet.append(["South", 120, 90, 230])

    nested_sheet = workbook.create_sheet("Nested")
    nested_sheet.append(["Department", "Team", "Metric", "Jan", "Feb"])
    nested_sheet.append(["Sales", "Enterprise", "Pipeline", 10, 11])
    nested_sheet.append([None, "SMB", "Pipeline", 5, 7])

    input_path = tmp_path / "sample.xlsx"
    workbook.save(input_path)

    outputs = core.convert_document_to_ingestion_outputs(
        input_path=input_path,
        output_dir=tmp_path / "out-xlsx",
    )

    _assert_source_sidecar_contract(
        outputs,
        expected_input_type="xlsx",
        expected_pipeline_family="spreadsheet",
    )
    manifest = outputs["manifest"]
    assert manifest["spreadsheet"]["sheet_count"] == 2
    assert manifest["page_count"] == manifest["spreadsheet"]["sheet_count"]
    assert manifest["spreadsheet"]["table_count"] >= 2
    assert manifest["spreadsheet"]["merged_cell_count"] >= 3
    assert manifest["spreadsheet"]["has_merged_cells"] is True
    assert manifest["spreadsheet"]["has_multi_sheet"] is True
    assert "FY2026 Revenue Plan" in outputs["markdown_text"]
    assert "Department" in outputs["markdown_text"]
    assert outputs["manifest"]["quality"]["agent_ready"] is True

    tables = outputs["docling_document"]["tables"]
    assert len(tables) >= 2
    cells = [
        cell
        for table in tables
        for cell in table["data"]["table_cells"]
    ]
    assert any(cell["col_span"] > 1 for cell in cells)
    assert any(cell["row_span"] > 1 for cell in cells)

    docling_json = json.loads(outputs["docling_json_path"].read_text(encoding="utf-8"))
    docling_text_values = _docling_json_text_values(docling_json)
    assert {"FY2026 Revenue Plan", "Region", "Department", "North"}.issubset(docling_text_values)


def test_convert_document_smoke_converts_real_csv_file(tmp_path: Path):
    input_path = tmp_path / "sample.csv"
    input_path.write_text(
        "Region,Online,Retail\nNorth,100,80\nSouth,120,90\n",
        encoding="utf-8",
    )

    outputs = core.convert_document_to_ingestion_outputs(
        input_path=input_path,
        output_dir=tmp_path / "out-csv",
    )

    _assert_source_sidecar_contract(
        outputs,
        expected_input_type="csv",
        expected_pipeline_family="spreadsheet",
    )
    assert outputs["manifest"]["spreadsheet"]["source_format"] == "csv"
    assert outputs["manifest"]["spreadsheet"]["sheet_count"] == 1
    assert outputs["manifest"]["spreadsheet"]["table_count"] >= 1
    assert "Region" in outputs["markdown_text"]
    assert "North" in outputs["markdown_text"]
    assert outputs["manifest"]["quality"]["agent_ready"] is True

    docling_json = json.loads(outputs["docling_json_path"].read_text(encoding="utf-8"))
    docling_text_values = _docling_json_text_values(docling_json)
    assert {"Region", "Online", "Retail", "North", "South"}.issubset(docling_text_values)


def _write_sample_xls_fixture(path: Path) -> None:
    compressed_xls = (
        "eNrtWEtIVFEY/s51nuJjNA00sEHIylyUQbTRKUldZWZBD4K65qEGx6tcb0FtsmyWQdSqaCO4aWO16UEPatciMGoR"
        "BMFYtGoVFLRQb//577mmNQsHcsi43+X85z//454z5//PY+7r6arcxL36GfyGdpRg3o0jskgmqMT9RgKkd13F+nWM"
        "ihtgVSEeo0BGwnhc/iqqYqjiPQMDd0MviAIfqRzDCHqGLZksIjp4DKZQY2gTIco9A7eoVKCOx1XN9CTTNUzvsO0T"
        "prtYcoVpG9nmxFFMp3qad+o8Pmw0sq6CqMAD9nnPkm2oxUuVxxeuCs82jN122sz8m4qGUBkmQZHrlpa0zUwONRTC"
        "SXx3k8A3f60+Twby4soFSP5jqTyaR37dCAFjcE8IlYhZVGJ9SGmi6JNnpXVGZilHoxFvZfbIUUcOzELyLhzn/EXX"
        "kdatrTuS2pws++Sp9LBFzD4rk7Y8iWOmM2HQIrad06XAHjli2s6QtBzq7KA0h0h3wMzIUdJ1Wo60R+z0qCxVnfD2"
        "kFiyPZTzoikjOkDjVXwVL50EHQCzt7++2dvfmzrOkjE+EryDY4P6pXBxUXmQcwVrShZoM3tsYXqJ37qO+XqmNZTw"
        "VDf11mqma5xtLrO2ifrZznib2riI30R89sv+hw3ZT6nNxE91z5yvmXqXmkAjTd8A+atnHC2iRdy8ofAo5ddCbzEf"
        "mNb9sd3EjIQeu6tPx0rMoZTZKqbPuKVmR82Pshd57AXbK+q1/Nn0Wga1SnRvRh5vg73VzD7l8Srva0LJOoga+Kx7"
        "UDDQblTjvnKhDfIXihFnY4Gu1jgbeeMc1pHy4hzR9iKPvRfn6JI4q1njmCBfTAIECBAgQIAAAVYEQl/L1CVTXdzC"
        "+vIX1d915qjMB59J/lv0YZgeh/6WdsKi2sa5gvJnLcLCf5dYpo//vVDhEPVuYxD9PI7BgvOXLu9i8e9ZtmPi7y2h"
        "QvufL2ScK9z/T0swDs0="
    )
    path.write_bytes(zlib.decompress(base64.b64decode(compressed_xls)))


def test_convert_document_smoke_converts_real_xls_file(tmp_path: Path):
    input_path = tmp_path / "sample.xls"
    _write_sample_xls_fixture(input_path)

    outputs = core.convert_document_to_ingestion_outputs(
        input_path=input_path,
        output_dir=tmp_path / "out-xls",
    )

    _assert_source_sidecar_contract(
        outputs,
        expected_input_type="xls",
        expected_pipeline_family="spreadsheet",
    )
    assert outputs["manifest"]["spreadsheet"]["source_format"] == "xls"
    assert outputs["manifest"]["spreadsheet"]["normalized_from"] == "xls"
    assert outputs["manifest"]["spreadsheet"]["sheet_count"] == 2
    assert outputs["manifest"]["spreadsheet"]["table_count"] >= 2
    assert outputs["manifest"]["spreadsheet"]["merged_cell_count"] >= 1
    assert "FY2026 Revenue" in outputs["markdown_text"]
    assert "Region" in outputs["markdown_text"]
    assert "Department" in outputs["markdown_text"]
    assert outputs["manifest"]["quality"]["agent_ready"] is True

    docling_json = json.loads(outputs["docling_json_path"].read_text(encoding="utf-8"))
    docling_text_values = _docling_json_text_values(docling_json)
    assert {"FY2026 Revenue", "Region", "Department", "North"}.issubset(docling_text_values)


def test_convert_text_native_txt_uses_string_conversion_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    input_path = tmp_path / "sample.txt"
    input_path.write_text("Plain text body.", encoding="utf-8")
    calls: list[tuple[str, InputFormat, str | None]] = []

    class FakeDocument:
        def export_to_markdown(self, image_mode=None) -> str:
            return "# Title\n\nPlain text body.\n"

        def export_to_dict(self) -> dict[str, object]:
            return {
                "schema_name": "DoclingDocument",
                "body": "Plain text body.",
            }

    class FakeResult:
        status = ConversionStatus.SUCCESS
        document = FakeDocument()
        pages: list[object] = []

    class FakeConverter:
        def __init__(self, allowed_formats=None):
            self.allowed_formats = allowed_formats

        def convert(self, source):
            raise AssertionError("txt should not use path-based convert()")

        def convert_string(self, content: str, format: InputFormat, name: str | None = None):
            calls.append((content, format, name))
            return FakeResult()

    monkeypatch.setattr(core, "DocumentConverter", FakeConverter)
    monkeypatch.setattr(core, "_collect_picture_sidecars", lambda document: [])

    attempt, attempts = core._convert_text_native_input(
        input_path,
        input_type="txt",
    )

    assert calls == [("Plain text body.", InputFormat.MD, "sample.md")]
    assert attempt.manifest["input_type"] == "txt"
    assert attempt.manifest["pipeline_family"] == "simple"
    assert attempt.manifest["quality"]["status"] == "good"
    assert attempt.structured_document["schema_name"] == "DoclingDocument"
    assert attempts == [attempt.manifest]
