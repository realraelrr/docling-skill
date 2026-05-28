---
name: docling-skill
description: Use when converting local documents with docling-skill into agent-ready source.* sidecar outputs, especially PDF, DOCX, XLS, XLSX, CSV, HTML, TXT, or Markdown inputs that need manifest-gated Markdown, structured Docling JSON, image sidecars, OCR remediation, or local document pre-ingestion for downstream knowledge-base workflows.
---

# docling-skill

Convert local documents into a stable `source.*` sidecar set for agent consumption. Treat this skill as the ingestion layer, not as ad hoc text extraction.

## Preconditions
- If you use the relative command, run from the `docling-skill` repo root.
- Runtime: `conda` environment `docling`, or pip-installed `docling-skill` CLI.
- Always provide an explicit output directory.

## Command

Conda environment:

```bash
conda run -n docling python \
  -m docling_skill.cli \
  "<input_path>" \
  "<output_dir>"
```

Or if installed via pip:

```bash
docling-skill "<input_path>" "<output_dir>"
```

Optional flags:

```bash
--ocr-engine auto|tesseract|ocrmac|rapidocr
--ocr-lang <lang>          # repeatable or comma-separated
--force-full-page-ocr
--no-ocr-remediation
```

Inputs:

- `input_path`: Absolute or repo-relative local document path. Supported inputs: `pdf`, `docx`, `xls`, `xlsx`, `csv`, `html`, `txt`, and `md`.
- `output_dir`: Explicit directory where outputs should be written.

## Outputs
The extractor writes:

- `source.md`
- `source.docling.json`
- `source.images.json`
- `source.manifest.json`
- `source.meta.json`

Use `source.manifest.json` before trusting any other output.

Artifact roles:

- `source.manifest.json`: Quality, trust, routing, remediation, `preferred_agent_artifact`, `authoritative_artifact`, `available_artifacts`, and selected attempt metadata.
- `source.md`: Default agent-readable Markdown. Image placeholders appear as `[[image:picture-p3-0]]`.
- `source.docling.json`: Authoritative structured Docling export from the same conversion result as `source.md`; use for recovery, machine-readable structure, or deeper inspection.
- `source.images.json`: Extracted image sidecars with `id`, `placeholder`, `page_no`, `bbox`, `mime_type`, and `base64` when image extraction is available.
- `source.meta.json`: Ingestion metadata only: `job_id`, `input_type`, `source_title`, `source_url`, `source_attachment`, `author`, `published_at`, `extractor`, `pipeline_family`, `quality_status`, `quality_reasons`, and `char_count`.

Do not add downstream knowledge fields such as tags, keywords, category, summary, or embeddings to `source.meta.json`.

## Workflow Boundary

- `docling-skill` is the ingestion layer, not the full workflow.
- It emits `source.*` directly instead of `<stem>.*`.
- It does not do chunking. Chunking belongs to the shared normalize stage after ingestion.
- It does not emit knowledge-base semantic fields.
- It does not fetch remote URLs. Remote acquisition belongs to the fetcher/browser layer upstream.

## Manifest Check
Read `source.manifest.json` before consuming `source.md`:

Minimum fields to inspect:

- `manifest["quality"]["status"]`
- `manifest["quality"]["reasons"]`
- `manifest["quality"]["content_trust"]`
- `manifest["preferred_agent_artifact"]`
- `manifest["authoritative_artifact"]`
- `manifest["available_artifacts"]`
- `manifest["selected_attempt"]`

```bash
python3 -c 'import json, pathlib; p = pathlib.Path("PATH_TO_MANIFEST"); m = json.loads(p.read_text(encoding="utf-8")); print({"status": m["quality"]["status"], "agent_ready": m["quality"]["agent_ready"], "reasons": m["quality"]["reasons"], "selected_attempt": m["selected_attempt"], "ocr_remediation_applied": m["ocr_remediation_applied"]})'
```

## Decision Flow
1. Resolve the input document path and an explicit output directory.
2. Run the extractor.
3. Read `source.manifest.json` before trusting `source.md`.
4. Decide from `manifest["quality"]["status"]`:
   - `good`: use `source.md` as the primary text artifact.
   - `salvaged`: use `source.md`, but treat it as OCR-remediated and lower confidence.
   - `failed_for_agent`: do not present it as clean ingestion; report the failure and the manifest reasons.
   - For text-native inputs, `good` means usable structure survived in Markdown; it is not just "the parse succeeded" or "the Markdown is non-empty."
   - For `docx`, `html`, and `md`, accept surviving paragraph/body structure, including concise body text, or preserved list structure when the list is the document's real content; `txt` stays looser.
5. Treat `manifest["preferred_agent_artifact"]` as the default agent entrypoint. In this contract that is always `source.md`.
6. Treat `manifest["authoritative_artifact"]` as the recovery/deep-inspection artifact. In this contract that is always `source.docling.json`.
7. Check `manifest["selected_attempt"]` to see which attempt won. A remediation attempt can still end as `failed_for_agent`.
8. If image analysis matters, resolve placeholders through `source.images.json`.

## Images
When analysis depends on a specific figure or chart:
1. Find the placeholder in `.md`, for example `[[image:picture-p2-1]]`.
2. Look up the matching entry in `source.images.json` by `id` or `placeholder`.
3. Pass the corresponding base64 image through the current runtime's supported multimodal input path.

Image handling notes:
- Embedded images in local PDFs are supported.
- Image extraction is not universal across all supported formats.
- HTML and webpage image capture should be owned by the fetcher/browser layer, not this ingestion step.

## Spreadsheets

For `xls`, `xlsx`, and `csv` inputs:
- Treat `source.md` as a readable preview.
- Use `source.docling.json` as the required authoritative artifact when merged cells, multi-row headers, multiple sheets, table spans, or cell offsets matter.
- Check `manifest["spreadsheet"]` for `source_format`, `sheet_count`, `table_count`, `merged_cell_count`, `has_merged_cells`, and `has_multi_sheet`. `normalized_from` is conditional and appears only when a source format was normalized before ingestion, for example from `xls` to `xlsx`.
- Do not infer merged or nested table semantics from Markdown alone; Markdown may flatten or visually repeat merged values.
- Formula evaluation is not guaranteed; spreadsheets that depend on recalculation or contain stale cached formula values should be manually preprocessed into clean `xlsx` or `csv` before ingestion.
- Macro-enabled workbooks (`xlsm`), password-protected files, corrupt files, chart/image semantics, and unusually complex workbooks should be manually preprocessed into clean `xlsx` or `csv` before ingestion.

Example listing command:

```bash
python3 -c 'import json, pathlib; imgs = json.loads(pathlib.Path("PATH_TO_IMAGES_JSON").read_text(encoding="utf-8")); [print({"placeholder": img["placeholder"], "page_no": img["page_no"], "base64_len": len(img["base64"])}) for img in imgs]'
```

## Examples
Basic conversion:

```bash
conda run -n docling python -m docling_skill.cli \
  "/path/to/file.docx" \
  "/tmp/docling-sidecar"
```

PDF OCR with explicit language and output path:

```bash
conda run -n docling python -m docling_skill.cli \
  "/path/to/chinese-file.pdf" \
  "/tmp/docling-sidecar-cn" \
  --ocr-engine tesseract \
  --ocr-lang chi_sim
```

## Success Signal
- The command exits with code `0`.
- The output directory contains `source.md`, `source.docling.json`, `source.images.json`, `source.manifest.json`, and `source.meta.json`.
- `source.manifest.json` has been checked explicitly before using `source.md`.

## Scope

OCR flags are mainly relevant for PDF inputs. Text-native formats such as DOCX, HTML, TXT, and Markdown, and spreadsheet formats such as XLS, XLSX, and CSV, typically do not need the PDF remediation path.

Docling itself supports more formats upstream, but those remain out of scope for this workflow phase unless they are explicitly added to the local `source.*` contract here.

## Integration
- Root source: `SKILL.md`.
- Codex entrypoint: `.codex/skills/docling-skill/SKILL.md` or `~/.codex/skills/docling-skill/SKILL.md`.
- Claude Code entrypoint: `.claude/skills/docling-skill/SKILL.md` or `~/.claude/skills/docling-skill/SKILL.md`.
- Prefer symlinks to this repo when installing the same source skill for both runtimes.

## Common Mistakes
- Do not skip the manifest check.
- Do not assume `selected_attempt` or a remediation attempt means the result is usable.
- Do not treat `failed_for_agent` as clean ingestion; it can still contain a small readable preview.
- Do not embed image base64 into Markdown manually; this tool already writes `source.images.json`.
- Do not omit the output directory.
