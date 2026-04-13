# docling-skill

`docling-skill` is a local, agent-first document normalization and ingestion layer built on top of [Docling](https://github.com/docling-project/docling).

[中文说明](README.zh-CN.md)

It turns a local document artifact into workflow-ready artifacts that LLM agents can consume directly:

- `source.md`: agent-readable markdown
- `source.docling.json`: structured Docling document export from the same conversion result as `source.md`
- `source.images.json`: image sidecars with stable placeholders and base64 payloads when extraction is available
- `source.manifest.json`: quality, remediation, and routing metadata
- `source.meta.json`: lightweight ingestion metadata for downstream agents

The key idea is simple: agents should not trust extracted markdown blindly. They should read the manifest first, then decide whether the result is safe to use. Once the manifest says the extraction is usable, agents read `source.md` first; systems recover or deepen from `source.docling.json` when they need structure that Markdown flattened away.

## Workflow Boundary

`docling-skill` is the ingestion layer for a larger workflow. Its contract is intentionally narrow:

- It emits `source.*` ingestion artifacts directly.
- It currently accepts local `pdf`, `docx`, `html`, `txt`, and `md` inputs.
- It keeps manifest-first quality gating as the control plane.
- It does not do chunking. Chunking belongs to the generic normalization stage after ingestion.
- It does not emit knowledge-base semantic fields such as tags, keywords, category, or one-line summary.
- It does not fetch remote URLs. Remote acquisition belongs to the fetcher/browser layer upstream.

## Why This Exists

Docling is strong at document parsing. `docling-skill` adds the agent-facing contract around it:

- manifest-first consumption
- stable image placeholders like `[[image:picture-p3-0]]`
- agent-quality gating
- OCR remediation for PDF workflows
- page-level remediation for weak pages inside otherwise good documents
- explicit result taxonomy: `good`, `salvaged`, `failed_for_agent`

This repository is intentionally a thin layer on top of official `docling`, not a long-lived fork of the full upstream project.

## Quickstart

```bash
pip install "git+https://github.com/realraelrr/docling-skill.git@v0.1.0"
docling-skill "/path/to/file.pdf" "/tmp/docling-sidecar"
```

If your runtime uses SOCKS proxies, prefer:

```bash
pip install "git+https://github.com/realraelrr/docling-skill.git@v0.1.0"
pip install socksio
```

For local development:

```bash
git clone https://github.com/realraelrr/docling-skill.git
cd docling-skill
pip install -e .
```

## Homepage Example

Convert a local document:

```bash
docling-skill "/path/to/file.docx" "/tmp/docling-sidecar"
```

Inspect the manifest before using the markdown:

```bash
python3 -c 'import json, pathlib; p = pathlib.Path("/tmp/docling-sidecar/source.manifest.json"); m = json.loads(p.read_text(encoding="utf-8")); print({"status": m["quality"]["status"], "reasons": m["quality"]["reasons"], "selected_attempt": m["selected_attempt"]})'
```

Typical output:

```json
{
  "status": "good",
  "reasons": [],
  "selected_attempt": "primary"
}
```

Only after that should downstream consumers use the outputs:

- Agents read `/tmp/docling-sidecar/source.md` first.
- Systems recover or deepen from `/tmp/docling-sidecar/source.docling.json` when they need authoritative structure.
- Multimodal flows resolve placeholders through `/tmp/docling-sidecar/source.images.json`.
- Orchestrators can read `/tmp/docling-sidecar/source.meta.json`.

## CLI

```bash
docling-skill "<input_path>" "<output_dir>"
```

Equivalent module entrypoint:

```bash
python -m docling_skill.cli "<input_path>" "<output_dir>"
```

Optional flags:

```bash
--ocr-engine auto|tesseract|ocrmac|rapidocr
--ocr-lang <lang>
--force-full-page-ocr
--no-ocr-remediation
```

## Python API

```python
from pathlib import Path

from docling_skill import convert_document_to_ingestion_outputs

outputs = convert_document_to_ingestion_outputs(
    input_path=Path("/path/to/file.html"),
    output_dir=Path("/tmp/docling-sidecar"),
)

manifest = outputs["manifest"]
if manifest["quality"]["status"] != "good":
    raise RuntimeError(manifest["quality"])

markdown_text = outputs["markdown_text"]
docling_document = outputs["docling_document"]
images = outputs["images"]
meta = outputs["meta"]
```

## Output Contract

The CLI writes:

- `source.md`
- `source.docling.json`
- `source.images.json`
- `source.manifest.json`
- `source.meta.json`

`source.manifest.json` is the control plane for downstream agents.
`source.docling.json` is the authoritative structured sidecar for consumers that need machine-readable document structure or a recovery path beyond Markdown.
`source.meta.json` is the bridge metadata for downstream agents and orchestrators.

Important fields:

- `manifest["quality"]["status"]`
- `manifest["quality"]["agent_ready"]`
- `manifest["quality"]["reasons"]`
- `manifest["quality"]["content_trust"]`
- `manifest["preferred_agent_artifact"]`
- `manifest["authoritative_artifact"]`
- `manifest["available_artifacts"]`
- `manifest["selected_attempt"]`
- `manifest["ocr_remediation_applied"]`

Downstream rule:

- Read `source.manifest.json` first.
- If the manifest is usable, agents read `source.md` first.
- If a system needs to recover structure, reconcile ambiguous Markdown, or inspect layout-aware detail, use `source.docling.json`.

Status meanings:

- `good`: safe default for downstream agent consumption
- `salvaged`: usable, but selected from a remediation path
- `failed_for_agent`: do not present as clean ingestion

For text-native inputs, `good` means the converted Markdown still preserves usable body structure.
It is not equivalent to "Docling parsed the file" or "the Markdown is merely non-empty."
For `docx`, `html`, and `md`, the quality gate accepts surviving paragraph/body structure, including concise body text, or preserved list structure where that is the real content.
For `txt`, the gate stays looser because plain text often has less explicit structure.

`source.meta.json` intentionally stays limited to ingestion metadata:

- `job_id`
- `input_type`
- `source_title`
- `source_url`
- `source_attachment`
- `author`
- `published_at`
- `extractor`
- `pipeline_family`
- `quality_status`
- `quality_reasons`
- `char_count`

It does not include downstream knowledge fields such as tags, keywords, category, or summary.

## Image Sidecars

Markdown includes placeholders such as `[[image:picture-p2-1]]`.

Image extraction is not universal across all supported formats. Use the placeholder to resolve the matching entry in `source.images.json` when an image sidecar entry is present, then pass the image through your runtime's multimodal input path.

Current image guidance:

- Embedded images in local PDFs are supported.
- Some other local formats may yield image sidecars when Docling exposes them, but do not assume parity across formats.
- HTML and webpage image capture should be owned by the fetcher/browser layer in the larger workflow, not by this ingestion step.

Each image record includes:

- `id`
- `placeholder`
- `page_no`
- `bbox`
- `mime_type`
- `base64`

## Design Principles

- Markdown should stay text-first and never inline image base64.
- Agents should make trust decisions from the manifest, not from ad hoc heuristics downstream.
- OCR remediation should be explicit and inspectable when used.
- Page-level remediation is better than rerunning the whole document when only a few pages are weak.

## Upstream Boundary

`docling-skill` depends on official `docling`.

The current local workflow contract supports `pdf`, `docx`, `html`, `txt`, and `md`.

OCR flags are mainly relevant for PDF inputs. Text-native formats such as DOCX, HTML, TXT, and Markdown typically do not need the PDF remediation path.

Docling itself supports many more formats. Those broader upstream capabilities remain out of scope for this workflow phase unless they are explicitly added to the local `source.*` contract here.

There is currently one known gap between this package and the `pdf-ingest` working fork:

- the fork contains a shared-layer SOCKS proxy compatibility patch in `hf_model_download.py`
- that patch is not copied into `docling-skill`

See [UPSTREAM_GAPS.md](UPSTREAM_GAPS.md) for the current migration note.
