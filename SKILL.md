---
name: docling-skill
description: Use when converting documents with docling-skill into workflow-ready sidecar outputs, especially when the caller needs Markdown, image sidecars, OCR remediation, or manifest-based quality checks.
---

# docling-skill

## When to use
- A document needs to be converted for agent consumption rather than ad hoc text extraction.
- The caller needs Markdown, structured Docling JSON, image sidecars, and a quality manifest.
- The source may be scanned, image-heavy, or likely to require OCR remediation, especially for PDF.
- The user asks for document conversion, PDF extraction, PDF-to-Markdown, PDF analysis, or knowledge-base ingestion from a document.

## Preconditions
- If you use the relative command, run from the `docling-skill` repo root.
- Runtime: `conda` environment `docling`
- Always provide an explicit output directory unless the user explicitly accepts `/tmp/docling-output`.

## Canonical Command

```bash
conda run -n docling python \
  -m docling_skill.cli \
  "<input_path>" \
  "<output_dir>"
```

Optional flags:

```bash
--ocr-engine auto|tesseract|ocrmac|rapidocr
--ocr-lang <lang>          # repeatable or comma-separated
--force-full-page-ocr
--no-ocr-remediation
```

## Inputs
- `input_path`: Absolute or repo-relative document path.
  Supported local inputs: `pdf`, `docx`, `html`, `txt`, `md`.
- `output_dir`: Directory where outputs should be written.

## Outputs
The extractor writes:
- `source.md`
- `source.docling.json`
- `source.images.json`
- `source.manifest.json`
- `source.meta.json`

`source.md`
- Main agent-readable text.
- Images appear as placeholders like `[[image:picture-p3-0]]`.

`source.images.json`
- One entry per extracted picture when image extraction is available for that input.
- Includes `id`, `placeholder`, `page_no`, `bbox`, `mime_type`, and `base64`.

`source.docling.json`
- Structured Docling document export from the same conversion result as `source.md`.
- Agents should still read `source.md` first after the manifest check.
- Use `source.docling.json` when a downstream system needs authoritative machine-readable structure, recovery, or deeper inspection beyond Markdown.

`source.manifest.json`
- Includes `quality` (with nested `content_trust`), `preferred_agent_artifact`, `authoritative_artifact`, `available_artifacts`, `selected_attempt`, and `ocr_remediation_applied`.
- Use this file to decide whether the result is safe to pass downstream.

`source.meta.json`
- Includes only ingestion metadata: `job_id`, `input_type`, `source_title`, `source_url`, `source_attachment`, `author`, `published_at`, `extractor`, `pipeline_family`, `quality_status`, `quality_reasons`, and `char_count`.
- Do not put downstream knowledge fields like tags, keywords, category, or summary into this file.

## Workflow Boundary

- `docling-skill` is the ingestion layer, not the full workflow.
- It emits `source.*` directly instead of `<stem>.*`.
- It does not do chunking. Chunking belongs to the shared normalize stage after ingestion.
- It does not emit knowledge-base semantic fields.
- It currently accepts local `pdf`, `docx`, `html`, `txt`, and `md` inputs.
- It does not fetch remote URLs. Remote acquisition belongs to the fetcher/browser layer upstream.
- This workflow phase emits `source.md`, `source.docling.json`, `source.images.json`, `source.manifest.json`, and `source.meta.json`.

## First Check
Read `source.manifest.json` before consuming `source.md`.

Example:

```bash
python3 -c 'import json, pathlib; p = pathlib.Path("PATH_TO_MANIFEST"); m = json.loads(p.read_text(encoding="utf-8")); print({"status": m["quality"]["status"], "agent_ready": m["quality"]["agent_ready"], "reasons": m["quality"]["reasons"], "selected_attempt": m["selected_attempt"], "ocr_remediation_applied": m["ocr_remediation_applied"]})'
```

Minimum fields to inspect:
- `manifest["quality"]["status"]`
- `manifest["quality"]["reasons"]`
- `manifest["quality"]["content_trust"]`
- `manifest["preferred_agent_artifact"]`
- `manifest["authoritative_artifact"]`
- `manifest["available_artifacts"]`
- `manifest["selected_attempt"]`

Minimal example:

```bash
python3 -c 'import json, pathlib; p = pathlib.Path("/tmp/docling-sidecar/source.manifest.json"); m = json.loads(p.read_text(encoding="utf-8")); print({"status": m["quality"]["status"], "reasons": m["quality"]["reasons"], "selected_attempt": m["selected_attempt"]})'
```

## Decision Flow
1. Resolve the input document path and an explicit output directory.
2. Run the extractor.
3. Read `source.manifest.json` before trusting `source.md`.
4. Decide from `manifest["quality"]["status"]`:
   - `good`: use `source.md` as the primary text artifact.
   - `salvaged`: use `source.md`, but treat it as OCR-remediated and lower confidence.
   - `failed_for_agent`: do not present it as clean ingestion; report the failure and the manifest reasons.
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

## Roadmap Note

The current local workflow contract supports `pdf`, `docx`, `html`, `txt`, and `md`.

OCR flags are mainly relevant for PDF inputs. Text-native formats such as DOCX, HTML, TXT, and Markdown typically do not need the PDF remediation path.

Docling itself supports more formats upstream, but those remain out of scope for this workflow phase unless they are explicitly added to the local `source.*` contract here.

## Common Mistakes
- Do not skip the manifest check.
- Do not assume `selected_attempt` or a remediation attempt means the result is usable.
- Do not treat `failed_for_agent` as clean ingestion; it can still contain a small readable preview.
- Do not embed image base64 into Markdown manually; this tool already writes `source.images.json`.
- Do not rely on the default output directory unless the user explicitly accepted it.
