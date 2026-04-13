import json
from pathlib import Path

import docling_skill.cli as cli
import docling_skill.core as core
from docling_core.types.doc import BoundingBox, CoordOrigin, Size
from docling_core.types.doc.document import DocItemLabel, DoclingDocument, ProvenanceItem


def _fake_attempt(input_path: Path) -> core.AttemptArtifacts:
    return core.AttemptArtifacts(
        markdown_text="# Title\n\nBody text for ingestion.\n",
        images=[],
        page_outputs={},
        structured_document={
            "schema_name": "DoclingDocument",
            "name": input_path.name,
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
            "input_type": "pdf",
            "pipeline_family": "standard_pdf",
            "quality": {
                "status": "good",
                "agent_ready": True,
                "reasons": [],
            },
            "page_quality": {},
        },
    )


def _fake_pdf_attempt(
    input_path: Path,
    *,
    attempt: str,
    markdown_text: str,
    quality_status: str,
    agent_ready: bool,
    reasons: list[str],
    non_placeholder_characters: int,
) -> core.AttemptArtifacts:
    return core.AttemptArtifacts(
        markdown_text=markdown_text,
        images=[],
        page_outputs={},
        structured_document={
            "schema_name": "DoclingDocument",
            "attempt": attempt,
            "name": input_path.name,
        },
        manifest={
            "source_file": str(input_path),
            "input_type": "pdf",
            "pipeline_family": "standard_pdf",
            "attempt": attempt,
            "status": "success",
            "page_count": 1,
            "image_count": 0,
            "text_characters": len(markdown_text),
            "document_markdown": "source.md",
            "images_json": "source.images.json",
            "ocr": {
                "enabled": True,
                "engine": "tesseract",
                "languages": ["eng"],
                "force_full_page_ocr": attempt != "primary",
            },
            "quality": {
                "status": quality_status,
                "agent_ready": agent_ready,
                "reasons": reasons,
                "placeholder_count": 0,
                "non_placeholder_characters": non_placeholder_characters,
                "min_required_text_characters": 120,
                "picture_count": 0,
                "content_trust": {
                    "ocr_noise_ratio": 0.0,
                    "line_structure_signal": 1.0,
                    "table_fragment_signal": 0.0,
                },
            },
            "page_quality": {},
        },
    )


def _structured_page_document(*, name: str, page_no: int, text: str) -> dict[str, object]:
    document = DoclingDocument(name=name)
    document.add_page(page_no, Size(width=100.0, height=100.0))
    document.add_text(
        label=DocItemLabel.PARAGRAPH,
        text=text,
        prov=ProvenanceItem(
            page_no=page_no,
            bbox=BoundingBox(
                l=0.0,
                t=0.0,
                r=10.0,
                b=10.0,
                coord_origin=CoordOrigin.TOPLEFT,
            ),
            charspan=(0, len(text)),
        ),
    )
    return document.export_to_dict()


def _quality_report(*, status: str = "good", agent_ready: bool = True) -> dict[str, object]:
    return {
        "status": status,
        "agent_ready": agent_ready,
        "reasons": [],
        "placeholder_count": 0,
        "non_placeholder_characters": 20,
        "min_required_text_characters": 1,
        "picture_count": 0,
        "content_trust": {
            "ocr_noise_ratio": 0.0,
            "line_structure_signal": 1.0,
            "table_fragment_signal": 0.0,
        },
    }


def test_cli_re_exports_core_entrypoints():
    assert (
        cli.convert_document_to_ingestion_outputs
        is core.convert_document_to_ingestion_outputs
    )
    assert cli.convert_pdf_to_sidecar_outputs is core.convert_pdf_to_sidecar_outputs
    assert cli.main.__module__ == "docling_skill.cli"


def test_package_exposes_project_root_constant():
    pyproject_path = Path(core.PROJECT_ROOT / "pyproject.toml")

    assert pyproject_path.exists()
    assert 'name = "docling-skill"' in pyproject_path.read_text(encoding="utf-8")


def test_cli_accepts_input_path_argument():
    parser = cli._build_parser()

    action_names = {action.dest for action in parser._actions}

    assert "input_path" in action_names


def test_output_contract_uses_source_sidecars(tmp_path, monkeypatch):
    input_path = tmp_path / "example.pdf"
    output_dir = tmp_path / "out"

    monkeypatch.setattr(
        core,
        "_convert_single_attempt",
        lambda *args, **kwargs: _fake_attempt(input_path),
    )
    monkeypatch.setattr(
        core,
        "_select_remediation_plan",
        lambda **kwargs: ([], None),
    )

    outputs = core.convert_document_to_ingestion_outputs(
        input_path=input_path,
        output_dir=output_dir,
    )

    assert outputs["markdown_path"].name == "source.md"
    assert outputs["images_path"].name == "source.images.json"
    assert outputs["docling_json_path"].name == "source.docling.json"
    assert outputs["manifest_path"].name == "source.manifest.json"
    assert outputs["meta_path"].name == "source.meta.json"
    assert outputs["docling_document"] == {
        "schema_name": "DoclingDocument",
        "name": input_path.name,
    }

    manifest = json.loads(outputs["manifest_path"].read_text(encoding="utf-8"))
    assert manifest["document_markdown"] == "source.md"
    assert manifest["images_json"] == "source.images.json"
    assert manifest["input_type"] == "pdf"
    assert manifest["pipeline_family"] == "standard_pdf"

    meta = json.loads(outputs["meta_path"].read_text(encoding="utf-8"))
    assert meta["input_type"] == "pdf"
    assert meta["pipeline_family"] == "standard_pdf"

    docling_json = json.loads(outputs["docling_json_path"].read_text(encoding="utf-8"))
    assert docling_json == outputs["docling_document"]


def test_pdf_remediation_selection_preserves_salvaged_manifest(tmp_path, monkeypatch):
    input_path = tmp_path / "example.pdf"
    output_dir = tmp_path / "out"
    primary_attempt = _fake_pdf_attempt(
        input_path,
        attempt="primary",
        markdown_text="thin",
        quality_status="failed_for_agent",
        agent_ready=False,
        reasons=["low_text_content"],
        non_placeholder_characters=4,
    )
    remediated_attempt = _fake_pdf_attempt(
        input_path,
        attempt="page_ocr_remediation",
        markdown_text="# Title\n\nRecovered document text after OCR remediation.\n",
        quality_status="good",
        agent_ready=True,
        reasons=[],
        non_placeholder_characters=46,
    )

    monkeypatch.setattr(
        core,
        "_convert_single_attempt",
        lambda *args, **kwargs: primary_attempt,
    )
    monkeypatch.setattr(
        core,
        "_select_remediation_plan",
        lambda **kwargs: ([1], {"attempt_label": "ocr_remediation"}),
    )
    monkeypatch.setattr(
        core,
        "_remediate_pages",
        lambda *args, **kwargs: remediated_attempt,
    )

    outputs = core.convert_document_to_ingestion_outputs(
        input_path=input_path,
        output_dir=output_dir,
    )

    manifest = outputs["manifest"]
    assert outputs["markdown_text"] == remediated_attempt.markdown_text
    assert outputs["docling_document"] == remediated_attempt.structured_document
    assert manifest["selected_attempt"] == "page_ocr_remediation"
    assert manifest["ocr_remediation_applied"] is True
    assert len(manifest["attempts"]) == 2
    assert manifest["attempts"][0]["attempt"] == "primary"
    assert manifest["attempts"][1]["attempt"] == "page_ocr_remediation"
    assert manifest["quality"]["status"] == "salvaged"
    assert "ocr_remediation_selected" in manifest["quality"]["reasons"]

    meta = outputs["meta"]
    assert meta["quality_status"] == "salvaged"


def test_merge_page_attempts_rebuilds_structured_document_for_remediated_pages(tmp_path):
    input_path = tmp_path / "example.pdf"
    primary_page_one_doc = _structured_page_document(
        name="primary-page-1",
        page_no=1,
        text="Primary page 1",
    )
    primary_page_two_doc = _structured_page_document(
        name="primary-page-2",
        page_no=2,
        text="Primary page 2 stale",
    )
    remediated_page_two_doc = _structured_page_document(
        name="remediated-page-2",
        page_no=2,
        text="Remediated page 2",
    )

    primary_attempt = core.AttemptArtifacts(
        markdown_text="Primary page 1\n\nPrimary page 2 stale",
        images=[],
        page_outputs={
            1: core.PageArtifacts(
                markdown_text="Primary page 1",
                images=[],
                quality=_quality_report(),
                structured_document=primary_page_one_doc,
            ),
            2: core.PageArtifacts(
                markdown_text="Primary page 2 stale",
                images=[],
                quality=_quality_report(status="failed_for_agent", agent_ready=False),
                structured_document=primary_page_two_doc,
            ),
        },
        structured_document=DoclingDocument.concatenate(
            [
                DoclingDocument.model_validate(primary_page_one_doc),
                DoclingDocument.model_validate(primary_page_two_doc),
            ]
        ).export_to_dict(),
        manifest={
            "source_file": str(input_path),
            "status": "success",
        },
    )

    merged_attempt = core._merge_page_attempts(
        primary_attempt,
        {
            2: core.PageArtifacts(
                markdown_text="Remediated page 2",
                images=[],
                quality=_quality_report(),
                structured_document=remediated_page_two_doc,
            )
        },
        remediation_ocr_metadata={
            "enabled": True,
            "engine": "tesseract",
            "languages": ["eng"],
            "force_full_page_ocr": True,
        },
    )

    merged_document = DoclingDocument.model_validate(merged_attempt.structured_document)
    merged_markdown = merged_document.export_to_markdown()

    assert merged_attempt.markdown_text == "Primary page 1\n\nRemediated page 2"
    assert "Primary page 1" in merged_markdown
    assert "Remediated page 2" in merged_markdown
    assert "Primary page 2 stale" not in merged_markdown
