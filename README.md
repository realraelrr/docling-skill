# docling-skill

`docling-skill` is the agent-facing extraction layer split out from this `pdf-ingest` work.

It keeps the parts that are specifically useful for LLM agents:

- Markdown plus image sidecars
- manifest-first consumption
- agent-quality gating
- OCR remediation and page-level remediation
- stable image placeholders such as `[[image:picture-p3-0]]`

It is designed as a thin package on top of official `docling`, not as a long-lived fork of the full upstream repository.

## Why A Separate Repo

The independent value here is not Docling's parsing core. It is the contract around how agents consume the output:

- `foo.md`
- `foo.images.json`
- `foo.manifest.json`

That contract, plus the quality/status taxonomy, is what should live in its own repo.

## Installation

Inside an environment that already supports `docling`:

```bash
pip install -e .
```

If your runtime uses SOCKS proxies, prefer:

```bash
pip install -e '.[proxy]'
```

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

## Output Contract

For `foo.pdf`, the CLI writes:

- `foo.md`
- `foo.images.json`
- `foo.manifest.json`

Always inspect `foo.manifest.json` before trusting `foo.md`.

Important fields:

- `manifest["quality"]["status"]`
- `manifest["quality"]["reasons"]`
- `manifest["quality"]["content_trust"]`
- `manifest["selected_attempt"]`

## Upstream Dependency Boundary

This package intentionally depends on official `docling`.

Current limitation:

- the `pdf-ingest` fork contains a shared-layer SOCKS proxy compatibility patch in `hf_model_download.py`
- that patch is not copied into `docling-skill`

See [UPSTREAM_GAPS.md](UPSTREAM_GAPS.md) for the current migration gap.
