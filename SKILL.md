---
name: docling-skill
description: Use when an agent needs to convert local PDF, Office, spreadsheet, HTML, text, Markdown, or image files into docling-skill source.* sidecars before downstream reasoning, retrieval, wiki ingestion, or handoff.
---

# docling-skill

Use `docling-skill` as the local ingestion gate for document files. It produces a `source.*` sidecar set and a manifest that must be checked before any agent consumes the content.

## Use When
- Input is a local file: `pdf`, `docx`, `pptx`, `xls`, `xlsx`, `csv`, `html`, `txt`, `md`, `png`, `jpg`, `jpeg`, `tif`, `tiff`, `bmp`, or `webp`.
- Downstream work needs Markdown plus quality evidence, structured Docling JSON, or image sidecars.
- The agent needs to decide whether conversion output is safe enough to use.

## Do Not Use When
- The source is a remote URL; fetch or browser capture belongs upstream.
- The task is chunking, summarization, tagging, embedding, or knowledge modeling.
- The file is `.doc`, `.ppt`, `.xlsm`, password-protected, corrupt, or a workbook that needs manual semantic preprocessing; ask for a clean `.docx`, `.pptx`, `.xlsx`, `.csv`, or PDF.

## Run
Always provide an explicit output directory.

```bash
conda run -n docling python -m docling_skill.cli "<input_path>" "<output_dir>"
```

If the CLI is installed directly:

```bash
docling-skill "<input_path>" "<output_dir>"
```

PDF OCR flags, only when needed:

```bash
--ocr-engine auto|tesseract|ocrmac|rapidocr
--ocr-lang <lang>  # repeatable or comma-separated
--force-full-page-ocr
--no-ocr-remediation
```

## Outputs
Expected files:

- `source.manifest.json`
- `source.md`
- `source.docling.json`
- `source.images.json`
- `source.meta.json`

Read `source.manifest.json` first. Treat `source.md` as the default agent artifact only after the manifest allows it. Treat `source.docling.json` as the authoritative recovery artifact for structure-sensitive work. Use `source.images.json` to resolve image placeholders such as `[[image:picture-p2-1]]`.

Do not add downstream fields such as tags, keywords, categories, summaries, embeddings, or chunk IDs to `source.meta.json`.

## Manifest Decision
Inspect these groups:

- Contract: `contract_version`, `producer`
- Quality: `quality.status`, `quality.risk_level`, `quality.agent_ready`, `quality.reasons`, `quality.warnings`, `quality.signals`, `quality.content_trust`, `quality.gate`, `quality.limitations`
- Artifacts: `preferred_agent_artifact`, `authoritative_artifact`, `available_artifacts`
- Attempt: `selected_attempt`, `ocr_remediation_applied`

Decision matrix:

| Manifest quality | Agent action |
| --- | --- |
| `good` + `low` | Use `source.md` as primary input. |
| `good` + `medium` | Use `source.md`, but inspect warnings/signals before relying on details. |
| `salvaged` | Use only as OCR-remediated medium-risk output. |
| `failed_for_agent` | Do not present as clean ingestion; report failure evidence. |

`agent_ready: true` means default-usable, not semantically proven.

## Format Checks
- PDF: inspect `signals.page_coverage` when page warnings exist, especially `failed_pages` and `first_page_failed`.
- Chinese-heavy output: inspect `signals.text_normalization` and `signals.text_integrity`.
- Spreadsheets: use `source.docling.json` and `manifest["spreadsheet"]` when merged cells, multi-sheet layout, spans, or offsets matter; Markdown is only a preview.
- Images: image-only output with no usable OCR text should be treated as high risk when the manifest says `failed_for_agent`.
- Figures/charts: resolve placeholders through `source.images.json`; image extraction is not universal across formats.

## Success Signal
- Command exits `0`.
- All five `source.*` files exist in the output directory.
- Manifest has been checked before using `source.md`.

## Failure Report
When ingestion is not clean, report:

- input path and input type
- command exit code or exception
- `quality.status`, `quality.risk_level`, `quality.reasons`, `quality.warnings`
- relevant `quality.signals`
- `selected_attempt` and whether OCR remediation was applied
