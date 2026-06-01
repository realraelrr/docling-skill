import importlib.metadata as package_metadata
import json
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

import pytest
from docling_core.types.doc import BoundingBox, CoordOrigin, Size
from docling_core.types.doc.document import DocItemLabel, DoclingDocument, ProvenanceItem

import docling_skill
import docling_skill.cli as cli
import docling_skill.core as core
from docling_skill import manifest as manifest_helpers


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


def _project_dependencies() -> list[str]:
    pyproject_path = Path(core.PROJECT_ROOT / "pyproject.toml")
    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    return pyproject["project"]["dependencies"]


def _version_tuple(version: str) -> tuple[int, ...]:
    numeric_prefix = version.split("+", maxsplit=1)[0].split("-", maxsplit=1)[0]
    return tuple(int(part) for part in numeric_prefix.split("."))


def test_docling_dependency_tracks_v2_96_release():
    dependencies = _project_dependencies()

    assert "docling>=2.96.0,<2.97.0" in dependencies
    assert "docling-core>=2.77.1,<3.0.0" in dependencies


def test_installed_docling_runtime_satisfies_project_floor():
    assert _version_tuple(package_metadata.version("docling")) >= (2, 96, 0)
    assert _version_tuple(package_metadata.version("docling-core")) >= (2, 77, 1)
    assert _version_tuple(package_metadata.version("docling-parse")) >= (6, 2, 0)


def test_cli_re_exports_core_entrypoints():
    assert cli.__all__ == [
        "convert_document_to_ingestion_outputs",
        "convert_pdf_to_sidecar_outputs",
        "main",
    ]
    assert (
        cli.convert_document_to_ingestion_outputs
        is core.convert_document_to_ingestion_outputs
    )
    assert cli.convert_pdf_to_sidecar_outputs is core.convert_pdf_to_sidecar_outputs
    assert cli.main.__module__ == "docling_skill.cli"


def test_core_public_surface_does_not_re_export_helper_modules():
    assert core.__all__ == [
        "convert_document_to_ingestion_outputs",
        "convert_pdf_to_sidecar_outputs",
        "build_source_meta",
        "detect_input_type",
        "infer_source_title",
    ]
    assert not hasattr(core, "_assess_agent_quality")
    assert not hasattr(core, "_build_ocr_options")
    assert not hasattr(core, "_export_structured_document")
    assert hasattr(core, "_convert_pdf_input")


def test_package_exposes_project_root_constant():
    pyproject_path = Path(core.PROJECT_ROOT / "pyproject.toml")

    assert pyproject_path.exists()
    assert 'name = "docling-skill"' in pyproject_path.read_text(encoding="utf-8")


def test_package_version_matches_pyproject():
    pyproject_path = Path(core.PROJECT_ROOT / "pyproject.toml")
    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    assert docling_skill.__version__ == pyproject["project"]["version"]


def test_cli_accepts_input_path_argument():
    parser = cli._build_parser()

    action_names = {action.dest for action in parser._actions}

    assert "input_path" in action_names


def test_cli_requires_explicit_output_dir():
    parser = cli._build_parser()

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["input.pdf"])

    assert exc_info.value.code == 2


def test_cli_summary_prints_quality_risk_level(capsys):
    cli._print_conversion_summary(
        Path("/tmp/example.pdf"),
        {
            "content_path": Path("/tmp/out/source.md"),
            "evidence_path": Path("/tmp/out/source.evidence.json"),
            "manifest_path": Path("/tmp/out/source.manifest.json"),
            "content_text": "# Title\n\nBody text.",
            "manifest": {
                "source": {"input_type": "pdf"},
                "decision": {
                    "status": "good",
                    "agent_ready": True,
                    "risk_level": "low",
                    "read_order": ["source.md"],
                },
            },
            "evidence": {
                "images": [],
                "selected_attempt": "primary",
                "ocr_remediation_applied": False,
            },
        },
    )

    output = capsys.readouterr().out
    assert "Quality: good (risk_level=low, agent_ready=True)" in output
    assert "Read order: source.md" in output
    assert "Evidence: source.evidence.json" in output


def test_build_attempt_manifest_keeps_heavy_fields_for_evidence_only():
    manifest = manifest_helpers._build_attempt_manifest(
        Path("/tmp/example.pdf"),
        input_type="pdf",
        pipeline_family="standard_pdf",
        attempt_label="primary",
        status="success",
        images=[],
        markdown_text="# Title\n\nBody text for ingestion.\n",
        ocr_metadata=None,
        quality=_quality_report(),
        page_outputs={},
        page_count=1,
    )

    assert manifest["contract_version"] == "2.0"
    assert "preferred_agent_artifact" not in manifest
    assert "authoritative_artifact" not in manifest
    assert "available_artifacts" not in manifest
    assert manifest["quality"]["risk_level"] == "low"
    assert manifest["quality"]["warnings"] == []
    assert manifest["quality"]["gate"] == "minimum_viability"
    assert "signals" in manifest["quality"]


def test_output_sidecars_are_written_atomically_on_serialization_failure(
    tmp_path,
    monkeypatch,
):
    input_path = tmp_path / "example.pdf"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    existing_files = {
        "source.md": "old markdown",
        "source.manifest.json": '{"old": "manifest"}',
        "source.evidence.json": '{"old": "evidence"}',
    }
    for filename, content in existing_files.items():
        (output_dir / filename).write_text(content, encoding="utf-8")

    bad_attempt = _fake_attempt(input_path)
    bad_attempt.markdown_text = "new markdown"
    bad_attempt.structured_document = {"not_json": object()}

    monkeypatch.setattr(
        core,
        "_dispatch_conversion",
        lambda *args, **kwargs: (bad_attempt, [bad_attempt.manifest]),
    )

    with pytest.raises(TypeError):
        core.convert_document_to_ingestion_outputs(
            input_path=input_path,
            output_dir=output_dir,
        )

    for filename, content in existing_files.items():
        assert (output_dir / filename).read_text(encoding="utf-8") == content


def test_output_sidecar_publish_preflights_non_file_targets(
    tmp_path,
    monkeypatch,
):
    input_path = tmp_path / "example.pdf"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "source.md").write_text("old markdown", encoding="utf-8")
    (output_dir / "source.evidence.json").mkdir()

    good_attempt = _fake_attempt(input_path)

    monkeypatch.setattr(
        core,
        "_dispatch_conversion",
        lambda *args, **kwargs: (good_attempt, [good_attempt.manifest]),
    )

    with pytest.raises(RuntimeError, match="not a regular file"):
        core.convert_document_to_ingestion_outputs(
            input_path=input_path,
            output_dir=output_dir,
        )

    assert (output_dir / "source.md").read_text(encoding="utf-8") == "old markdown"
    assert (output_dir / "source.evidence.json").is_dir()


def test_manifest_is_published_after_evidence_as_commit_marker(tmp_path, monkeypatch):
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "source.md").write_text("old markdown", encoding="utf-8")
    (output_dir / "source.evidence.json").write_text('{"old": "evidence"}', encoding="utf-8")
    (output_dir / "source.manifest.json").write_text('{"old": "manifest"}', encoding="utf-8")

    original_replace = Path.replace

    def fail_evidence_replace(self: Path, target: Path):
        if self.name == "source.evidence.json":
            raise RuntimeError("simulated evidence publish failure")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_evidence_replace)

    with pytest.raises(RuntimeError, match="simulated evidence publish failure"):
        core._write_sidecars_with_staging(
            output_dir,
            markdown_text="new markdown",
            manifest={"new": "manifest"},
            evidence={"new": "evidence"},
        )

    assert (output_dir / "source.manifest.json").read_text(encoding="utf-8") == '{"old": "manifest"}'


def test_successful_publish_removes_stale_v1_sidecars(tmp_path, monkeypatch):
    input_path = tmp_path / "example.pdf"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    for filename in ("source.docling.json", "source.images.json", "source.meta.json"):
        (output_dir / filename).write_text("stale", encoding="utf-8")

    good_attempt = _fake_attempt(input_path)

    monkeypatch.setattr(
        core,
        "_dispatch_conversion",
        lambda *args, **kwargs: (good_attempt, [good_attempt.manifest]),
    )

    core.convert_document_to_ingestion_outputs(
        input_path=input_path,
        output_dir=output_dir,
    )

    assert (output_dir / "source.md").exists()
    assert (output_dir / "source.manifest.json").exists()
    assert (output_dir / "source.evidence.json").exists()
    assert not (output_dir / "source.docling.json").exists()
    assert not (output_dir / "source.images.json").exists()
    assert not (output_dir / "source.meta.json").exists()


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

    assert outputs["content_path"].name == "source.md"
    assert outputs["evidence_path"].name == "source.evidence.json"
    assert outputs["manifest_path"].name == "source.manifest.json"
    assert "markdown_path" not in outputs
    assert "images_path" not in outputs
    assert "docling_json_path" not in outputs
    assert "meta_path" not in outputs
    assert outputs["evidence"]["structured_document"] == {
        "schema_name": "DoclingDocument",
        "name": input_path.name,
    }
    assert not (output_dir / "source.docling.json").exists()
    assert not (output_dir / "source.images.json").exists()
    assert not (output_dir / "source.meta.json").exists()

    manifest = json.loads(outputs["manifest_path"].read_text(encoding="utf-8"))
    assert manifest["contract_version"] == "2.0"
    assert manifest["artifacts"] == {
        "content": "source.md",
        "evidence": "source.evidence.json",
    }
    assert manifest["decision"]["read_order"] == ["source.md"]
    assert manifest["source"]["input_type"] == "pdf"
    assert manifest["source"]["pipeline_family"] == "standard_pdf"
    assert "quality" not in manifest
    assert "attempts" not in manifest
    assert "page_quality" not in manifest

    evidence = json.loads(outputs["evidence_path"].read_text(encoding="utf-8"))
    assert evidence == outputs["evidence"]
    assert evidence["structured_document"] == outputs["evidence"]["structured_document"]


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
    evidence = outputs["evidence"]
    assert outputs["content_text"] == remediated_attempt.markdown_text
    assert evidence["structured_document"] == remediated_attempt.structured_document
    assert manifest["decision"]["status"] == "salvaged"
    assert manifest["decision"]["risk_level"] == "medium"
    assert manifest["decision"]["read_order"] == ["source.md", "source.evidence.json"]
    assert "ocr_remediation_selected" in manifest["reasons"]
    assert "ocr_remediation_selected" in manifest["warnings"]
    assert "quality" not in manifest
    assert "attempts" not in manifest

    assert evidence["selected_attempt"] == "page_ocr_remediation"
    assert evidence["ocr_remediation_applied"] is True
    assert len(evidence["attempts"]) == 2
    assert evidence["attempts"][0]["attempt"] == "primary"
    assert evidence["attempts"][1]["attempt"] == "page_ocr_remediation"
    assert evidence["quality"]["status"] == "salvaged"
    assert "ocr_remediation_selected" in evidence["quality"]["reasons"]
    assert evidence["quality"]["risk_level"] == "medium"
    assert "ocr_remediation_selected" in evidence["quality"]["warnings"]


def test_pdf_attempt_fails_when_page_quality_fails_in_short_document(tmp_path):
    input_path = tmp_path / "example.pdf"
    page_one_doc = _structured_page_document(
        name="page-1",
        page_no=1,
        text="Primary page with enough readable text.",
    )
    page_two_doc = _structured_page_document(
        name="page-2",
        page_no=2,
        text="Thin page",
    )
    page_three_doc = _structured_page_document(
        name="page-3",
        page_no=3,
        text="Final page with enough readable text.",
    )
    fallback_document = DoclingDocument.concatenate(
        [
            DoclingDocument.model_validate(page_one_doc),
            DoclingDocument.model_validate(page_two_doc),
            DoclingDocument.model_validate(page_three_doc),
        ]
    )
    fallback_document.name = input_path.name

    attempt = core._assemble_attempt_from_pages(
        input_path,
        page_outputs={
            1: core.PageArtifacts(
                markdown_text="Readable first page. " * 12,
                images=[],
                quality=_quality_report(),
                structured_document=page_one_doc,
            ),
            2: core.PageArtifacts(
                markdown_text="thin",
                images=[],
                quality=_quality_report(status="failed_for_agent", agent_ready=False),
                structured_document=page_two_doc,
            ),
            3: core.PageArtifacts(
                markdown_text="Readable final page. " * 12,
                images=[],
                quality=_quality_report(),
                structured_document=page_three_doc,
            ),
        },
        fallback_document=fallback_document,
        original_document_name=input_path.name,
        attempt_label="primary",
        status="success",
        ocr_metadata={
            "enabled": True,
            "engine": "tesseract",
            "languages": ["eng"],
            "force_full_page_ocr": False,
        },
    )

    quality = attempt.manifest["quality"]
    assert quality["status"] == "failed_for_agent"
    assert quality["agent_ready"] is False
    assert quality["risk_level"] == "high"
    assert "page_quality_failed" in quality["reasons"]
    assert quality["signals"]["page_coverage"]["failed_pages"] == [2]


def test_pdf_attempt_warns_when_first_page_fails_in_long_document(tmp_path):
    input_path = tmp_path / "example.pdf"
    page_outputs: dict[int, core.PageArtifacts] = {}
    documents = []
    for page_no in range(1, 11):
        page_doc = _structured_page_document(
            name=f"page-{page_no}",
            page_no=page_no,
            text=f"Page {page_no}",
        )
        documents.append(DoclingDocument.model_validate(page_doc))
        page_outputs[page_no] = core.PageArtifacts(
            markdown_text=(
                "thin"
                if page_no == 1
                else f"Readable page {page_no} with enough natural text. " * 5
            ),
            images=[],
            quality=_quality_report(
                status="failed_for_agent",
                agent_ready=False,
            )
            if page_no == 1
            else _quality_report(),
            structured_document=page_doc,
        )
    fallback_document = DoclingDocument.concatenate(documents)
    fallback_document.name = input_path.name

    attempt = core._assemble_attempt_from_pages(
        input_path,
        page_outputs=page_outputs,
        fallback_document=fallback_document,
        original_document_name=input_path.name,
        attempt_label="primary",
        status="success",
        ocr_metadata={
            "enabled": True,
            "engine": "tesseract",
            "languages": ["eng"],
            "force_full_page_ocr": False,
        },
    )

    quality = attempt.manifest["quality"]
    assert quality["status"] == "good"
    assert quality["agent_ready"] is True
    assert quality["risk_level"] == "medium"
    assert "partial_page_quality_failed" in quality["warnings"]
    assert "first_page_quality_failed" in quality["warnings"]
    assert quality["signals"]["page_coverage"]["failed_pages"] == [1]
    assert quality["signals"]["page_coverage"]["first_page_failed"] is True


def test_pdf_attempt_fails_when_many_pages_fail_below_half_ratio(tmp_path):
    input_path = tmp_path / "example.pdf"
    page_outputs: dict[int, core.PageArtifacts] = {}
    documents = []
    failed_pages = set(range(1, 10))

    for page_no in range(1, 21):
        page_doc = _structured_page_document(
            name=f"page-{page_no}",
            page_no=page_no,
            text=f"Page {page_no}",
        )
        documents.append(DoclingDocument.model_validate(page_doc))
        page_outputs[page_no] = core.PageArtifacts(
            markdown_text=(
                "thin"
                if page_no in failed_pages
                else f"Readable page {page_no} with enough natural text. " * 5
            ),
            images=[],
            quality=_quality_report(
                status="failed_for_agent",
                agent_ready=False,
            )
            if page_no in failed_pages
            else _quality_report(),
            structured_document=page_doc,
        )
    fallback_document = DoclingDocument.concatenate(documents)
    fallback_document.name = input_path.name

    attempt = core._assemble_attempt_from_pages(
        input_path,
        page_outputs=page_outputs,
        fallback_document=fallback_document,
        original_document_name=input_path.name,
        attempt_label="primary",
        status="success",
        ocr_metadata={
            "enabled": True,
            "engine": "tesseract",
            "languages": ["eng"],
            "force_full_page_ocr": False,
        },
    )

    quality = attempt.manifest["quality"]
    assert quality["status"] == "failed_for_agent"
    assert quality["agent_ready"] is False
    assert quality["risk_level"] == "high"
    assert "page_quality_failed" in quality["reasons"]
    assert quality["signals"]["page_coverage"]["failed_page_count"] == 9
    assert quality["signals"]["page_coverage"]["failed_page_ratio"] == 0.45


def test_pdf_attempt_fails_when_first_page_quality_fails(tmp_path):
    input_path = tmp_path / "example.pdf"
    page_one_doc = _structured_page_document(name="page-1", page_no=1, text="Thin page")
    page_two_doc = _structured_page_document(
        name="page-2",
        page_no=2,
        text="Readable second page with enough text.",
    )
    fallback_document = DoclingDocument.concatenate(
        [
            DoclingDocument.model_validate(page_one_doc),
            DoclingDocument.model_validate(page_two_doc),
        ]
    )
    fallback_document.name = input_path.name

    attempt = core._assemble_attempt_from_pages(
        input_path,
        page_outputs={
            1: core.PageArtifacts(
                markdown_text="thin",
                images=[],
                quality=_quality_report(status="failed_for_agent", agent_ready=False),
                structured_document=page_one_doc,
            ),
            2: core.PageArtifacts(
                markdown_text="Readable second page. " * 12,
                images=[],
                quality=_quality_report(),
                structured_document=page_two_doc,
            ),
        },
        fallback_document=fallback_document,
        original_document_name=input_path.name,
        attempt_label="primary",
        status="success",
        ocr_metadata={
            "enabled": True,
            "engine": "tesseract",
            "languages": ["eng"],
            "force_full_page_ocr": False,
        },
    )

    quality = attempt.manifest["quality"]
    assert quality["status"] == "failed_for_agent"
    assert quality["agent_ready"] is False
    assert quality["risk_level"] == "high"
    assert "page_quality_failed" in quality["reasons"]
    assert quality["signals"]["page_coverage"]["failed_pages"] == [1]


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
        structured_document={
            **DoclingDocument.concatenate(
                [
                    DoclingDocument.model_validate(primary_page_one_doc),
                    DoclingDocument.model_validate(primary_page_two_doc),
                ]
            ).export_to_dict(),
            "name": input_path.name,
        },
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
    assert merged_document.name == input_path.name
    assert "Primary page 1" in merged_markdown
    assert "Remediated page 2" in merged_markdown
    assert "Primary page 2 stale" not in merged_markdown


def test_collect_page_outputs_does_not_export_per_page_structured_docs_eagerly(monkeypatch):
    class FakePage:
        def __init__(self, page_no: int):
            self.page_no = page_no

    class FakeDocument:
        def filter(self, page_nrs=None):
            raise AssertionError("page-level structured export should stay lazy")

    class FakeResult:
        document = FakeDocument()
        pages = [FakePage(1), FakePage(2)]

    monkeypatch.setattr(
        core,
        "_export_page_markdown",
        lambda result: {1: "Primary page 1", 2: "Primary page 2"},
    )
    monkeypatch.setattr(
        core,
        "_assess_page_qualities",
        lambda **kwargs: {1: _quality_report(), 2: _quality_report()},
    )

    page_outputs = core._collect_page_outputs(
        FakeResult(),
        pictures=[],
        full_markdown_text="Primary page 1\n\nPrimary page 2",
    )

    assert page_outputs[1].structured_document is None
    assert page_outputs[2].structured_document is None


def test_export_page_markdown_includes_last_item_on_each_page(monkeypatch):
    class FakeProvenance:
        def __init__(self, page: int):
            self.page = page

    class FakeItem:
        def __init__(self, text: str, page: int):
            self.text = text
            self.prov = [FakeProvenance(page)]

    class FakeLegacyDocument:
        def __init__(self):
            self.main_text = [
                FakeItem("p1-a", 1),
                FakeItem("p1-b", 1),
                FakeItem("p2-a", 2),
                FakeItem("p2-b", 2),
            ]

        def _resolve_ref(self, item):
            return item

        def export_to_markdown(self, *, main_text_start: int, main_text_stop: int) -> str:
            return "\n".join(
                item.text for item in self.main_text[main_text_start:main_text_stop]
            )

    class FakeResult:
        document = object()

    monkeypatch.setattr(
        core,
        "docling_document_to_legacy",
        lambda document: FakeLegacyDocument(),
    )

    page_markdown = core._export_page_markdown(FakeResult())

    assert page_markdown == {
        1: "p1-a\np1-b",
        2: "p2-a\np2-b",
    }
