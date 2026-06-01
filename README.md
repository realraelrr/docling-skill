# docling-skill

`docling-skill` is a local, agent-first ingestion layer built on top of [Docling](https://github.com/docling-project/docling). It converts local documents into a stable `source.*` sidecar contract that LLM agents can inspect before consuming.

[中文 README](README.zh-CN.md)

Use it when an agent needs risk-aware local PDF, Office, image, HTML, text, or
Markdown conversion before downstream reasoning, retrieval, wiki ingestion, or
handoff. The key output is not just Markdown; it is an inspectable manifest with
minimum viability gates, risk level, warnings, and a pointer to on-demand
evidence.

## What It Does

Supported local inputs: `pdf`, `docx`, `pptx`, `xls`, `xlsx`, `csv`, `html`, `txt`, `md`, `png`, `jpg`, `jpeg`, `tif`, `tiff`, `bmp`, and `webp`.

Legacy `.doc` and `.ppt` files are intentionally not supported. Save them as
`.docx`/`.pptx` or PDF before ingestion.

Each successful conversion writes an agent-only v2 sidecar set:

| Artifact | Purpose |
| --- | --- |
| `source.md` | Default agent-readable Markdown, with narrow CJK cleanup applied for agent use |
| `source.manifest.json` | Compact agent decision metadata and read order |
| `source.evidence.json` | On-demand structured Docling export, quality signals, attempts, coverage, image sidecars, and optional PDF audit evidence |

`source.manifest.json` includes top-level contract metadata for downstream
agents:

- `contract_version`: current sidecar contract version, currently `2.0`
- `producer.name`: `docling-skill`
- `producer.version`: package version that produced the sidecars
- `producer.docling_version` and `producer.docling_core_version`: parser runtime versions
- `decision`: `status`, `risk_level`, `agent_ready`, and `read_order`
- `source`: source file, attachment name, inferred title, input type, and pipeline family
- `artifacts`: the compact content and evidence filenames

Downstream rule:

1. Read `source.manifest.json` first.
2. Follow `decision.read_order`.
3. For low-risk `good` output, read only `source.md` by default.
4. For warnings, `salvaged`, `failed_for_agent`, image placeholders, structure recovery, or spreadsheet details, read `source.evidence.json`.

The automatic quality model is a risk screen, not a semantic audit. A low-risk
result means no hard failure was detected; it does not prove source fidelity or
complete source-to-Markdown alignment. Medium-risk `good` output is still
agent-usable by default, but its manifest `warnings` and evidence `quality.signals`
should be inspected.
For long PDFs, isolated page failures can be downgraded to medium risk instead
of hard failure; inspect `source.evidence.json` `quality.signals.page_coverage`, especially
`first_page_failed`, before relying on front matter, title, or abstract text.

For Chinese-heavy documents, `source.md` receives targeted Markdown cleanup for
CJK compatibility glyphs and abnormal spaces between Chinese characters. The
evidence records this under `quality.signals.text_normalization`, while
`source.evidence.json` keeps Docling's structured export for recovery and deeper
inspection.

Image inputs use the same agent-readiness gate as OCR-oriented extraction. An
image-only result with no usable OCR text is reported as high risk and
`failed_for_agent` rather than treated as clean ingestion.

`docling-skill` intentionally does not fetch remote URLs, chunk documents, or emit downstream knowledge fields such as tags, keywords, categories, or summaries.

## Install

```bash
pip install "git+https://github.com/realraelrr/docling-skill.git@v2.0.0"
docling-skill "/path/to/file.pdf" "/tmp/docling-sidecar"
```

If your environment uses SOCKS proxies:

```bash
pip install "docling-skill[proxy] @ git+https://github.com/realraelrr/docling-skill.git@v2.0.0"
```

For local development:

```bash
git clone https://github.com/realraelrr/docling-skill.git
cd docling-skill
pip install -e ".[proxy]"
```

## Use

CLI:

```bash
docling-skill "<input_path>" "<output_dir>"
```

Equivalent module entrypoint:

```bash
python -m docling_skill.cli "<input_path>" "<output_dir>"
```

PDF-oriented OCR options:

```bash
--ocr-engine auto|tesseract|ocrmac|rapidocr
--ocr-lang <lang>
--force-full-page-ocr
--no-ocr-remediation
--pdf-audit
```

`--pdf-audit` records audit intent for eligible native formats. PDF audit
rendering is a soft, currently unavailable evidence path; native conversion
remains the primary path.

Manifest check:

```bash
python3 -c 'import json, pathlib; p = pathlib.Path("/tmp/docling-sidecar/source.manifest.json"); m = json.loads(p.read_text(encoding="utf-8")); d = m["decision"]; print({"status": d["status"], "risk_level": d["risk_level"], "agent_ready": d["agent_ready"], "read_order": d["read_order"], "warnings": m["warnings"]})'
```

Python API:

```python
from pathlib import Path

from docling_skill import convert_document_to_ingestion_outputs

outputs = convert_document_to_ingestion_outputs(
    input_path=Path("/path/to/file.html"),
    output_dir=Path("/tmp/docling-sidecar"),
)

manifest = outputs["manifest"]
if not manifest["decision"]["agent_ready"]:
    raise RuntimeError(manifest)

if "source.evidence.json" in manifest["decision"]["read_order"]:
    print(outputs["evidence"]["quality"]["signals"])

content_text = outputs["content_text"]
structured_document = outputs["evidence"]["structured_document"]
images = outputs["evidence"]["images"]
```

## Skill Integration

This repository supports both Codex and Claude Code from the same source skill.

- Codex: `.codex/skills/docling-skill/SKILL.md`
- Claude Code: `.claude/skills/docling-skill/SKILL.md`
- Root source: `SKILL.md`

For global installs, use the same target layout under the user's home directory:

- Codex: `~/.codex/skills/docling-skill/SKILL.md`
- Claude Code: `~/.claude/skills/docling-skill/SKILL.md`

## Agent Setup

If you are Codex, Claude Code, or another LLM agent setting up this project from scratch:

1. Treat this repository as the source of truth.
2. Clone it into the user's local code workspace.
3. Install it into the existing conda environment named `docling`, using the `proxy` extra when SOCKS proxies are configured.
4. Point both agent skill entrypoints at this repo's root `SKILL.md`, preferably with symlinks instead of copies.
5. Validate the root skill and both installed skill paths with the validator available in the active runtime.
6. Run the test suite.
7. Do not commit `.state/` or other agent working files.

Expected verification:

```bash
# If the Codex skill validator is available:
conda run -n docling python "$HOME/.codex/skills/.system/skill-creator/scripts/quick_validate.py" .
conda run -n docling python "$HOME/.codex/skills/.system/skill-creator/scripts/quick_validate.py" .codex/skills/docling-skill
conda run -n docling python "$HOME/.codex/skills/.system/skill-creator/scripts/quick_validate.py" .claude/skills/docling-skill

conda run -n docling python -m ruff check .
PYTHONPATH="$PWD/src" conda run -n docling python -m pytest
```

## Scope

`docling-skill` is a thin workflow layer on top of official `docling`, not a Docling fork or official distribution.

The skill workflow contract lives in [SKILL.md](SKILL.md). Docling supports more formats than this project exposes; new formats should only be added when they preserve the local `source.*` contract, risk evidence model, and tests.

## Acknowledgements

Built on top of [Docling](https://github.com/docling-project/docling), which provides the parser, document model, and format support.
