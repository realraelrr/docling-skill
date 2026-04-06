# docling-skill

`docling-skill` is an agent-first PDF ingestion layer built on top of [Docling](https://github.com/docling-project/docling).

It turns a PDF into three artifacts that LLM agents can consume directly:

- `foo.md`: agent-readable markdown
- `foo.images.json`: extracted images with stable placeholders and base64 payloads
- `foo.manifest.json`: quality, remediation, and routing metadata

The key idea is simple: agents should not trust extracted markdown blindly. They should read the manifest first, then decide whether the result is safe to use.

## Why This Exists

Docling is strong at document parsing. `docling-skill` adds the agent-facing contract around it:

- manifest-first consumption
- stable image placeholders like `[[image:picture-p3-0]]`
- agent-quality gating
- OCR remediation
- page-level remediation for weak pages inside otherwise good documents
- explicit result taxonomy: `good`, `salvaged`, `failed_for_agent`

This repository is intentionally a thin layer on top of official `docling`, not a long-lived fork of the full upstream project.

## Quickstart

```bash
pip install -e .
docling-skill "/path/to/file.pdf" "/tmp/docling-sidecar"
```

If your runtime uses SOCKS proxies, prefer:

```bash
pip install -e '.[proxy]'
```

## Homepage Example

Convert a PDF:

```bash
docling-skill "/path/to/file.pdf" "/tmp/docling-sidecar"
```

Inspect the manifest before using the markdown:

```bash
python3 -c 'import json, pathlib; p = pathlib.Path("/tmp/docling-sidecar/file.manifest.json"); m = json.loads(p.read_text(encoding="utf-8")); print({"status": m["quality"]["status"], "reasons": m["quality"]["reasons"], "selected_attempt": m["selected_attempt"]})'
```

Typical output:

```json
{
  "status": "good",
  "reasons": [],
  "selected_attempt": "primary"
}
```

Only after that should an agent consume:

- `/tmp/docling-sidecar/file.md`
- `/tmp/docling-sidecar/file.images.json`

## CLI

```bash
docling-skill "<input_pdf>" "<output_dir>"
```

Equivalent module entrypoint:

```bash
python -m docling_skill.cli "<input_pdf>" "<output_dir>"
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

from docling_skill import convert_pdf_to_sidecar_outputs

outputs = convert_pdf_to_sidecar_outputs(
    pdf_path=Path("/path/to/file.pdf"),
    output_dir=Path("/tmp/docling-sidecar"),
)

manifest = outputs["manifest"]
if manifest["quality"]["status"] != "good":
    raise RuntimeError(manifest["quality"])

markdown_text = outputs["markdown_text"]
images = outputs["images"]
```

## Output Contract

For `foo.pdf`, the CLI writes:

- `foo.md`
- `foo.images.json`
- `foo.manifest.json`

`foo.manifest.json` is the control plane for downstream agents.

Important fields:

- `manifest["quality"]["status"]`
- `manifest["quality"]["agent_ready"]`
- `manifest["quality"]["reasons"]`
- `manifest["quality"]["content_trust"]`
- `manifest["selected_attempt"]`
- `manifest["ocr_remediation_applied"]`

Status meanings:

- `good`: safe default for downstream agent consumption
- `salvaged`: usable, but selected from a remediation path
- `failed_for_agent`: do not present as clean ingestion

## Image Sidecars

Markdown includes placeholders such as `[[image:picture-p2-1]]`.

Use that placeholder to resolve the matching entry in `foo.images.json`, then pass the image through your runtime's multimodal input path.

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
- OCR remediation should be explicit and inspectable.
- Page-level remediation is better than rerunning the whole document when only a few pages are weak.

## Upstream Boundary

`docling-skill` depends on official `docling`.

There is currently one known gap between this package and the `pdf-ingest` working fork:

- the fork contains a shared-layer SOCKS proxy compatibility patch in `hf_model_download.py`
- that patch is not copied into `docling-skill`

See [UPSTREAM_GAPS.md](UPSTREAM_GAPS.md) for the current migration note.
