from pathlib import Path

import docling_skill.cli as cli
import docling_skill.core as core


def test_cli_re_exports_core_entrypoint():
    assert cli.convert_pdf_to_sidecar_outputs is core.convert_pdf_to_sidecar_outputs
    assert cli.main.__module__ == "docling_skill.cli"


def test_package_exposes_project_root_constant():
    assert core.PROJECT_ROOT.name == "docling-skill"
    assert Path(core.PROJECT_ROOT / "pyproject.toml").exists()
