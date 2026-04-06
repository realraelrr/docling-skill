---
name: docling-skill
description: Use when converting PDFs with docling-skill into agent-readable sidecar outputs, especially when the caller needs Markdown, image sidecars, OCR remediation, or manifest-based quality checks.
---

# docling-skill

## When to use
- A PDF needs to be converted for agent consumption rather than ad hoc text extraction.
- The caller needs Markdown plus image sidecars and a quality manifest.
- The PDF may be scanned, image-heavy, or likely to require OCR remediation.
- The user asks for PDF conversion, PDF extraction, PDF-to-Markdown, PDF analysis, or knowledge-base ingestion from a PDF.

## Preconditions
- If you use the relative command, run from the `docling-skill` repo root.
- Runtime: `conda` environment `docling`
- Always provide an explicit output directory unless the user explicitly accepts `/tmp/docling-output`.

## Canonical Command
Preferred when already in the repo root:

```bash
conda run -n docling python -m docling_skill.cli "<input_pdf>" "<output_dir>"
```

If not already in the repo root:

```bash
conda run -n docling python \
  -m docling_skill.cli \
  "<input_pdf>" \
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
- `input_pdf`: Absolute or repo-relative PDF path.
- `output_dir`: Directory where outputs should be written.

## Outputs
For input `foo.pdf`, the extractor writes:
- `foo.md`
- `foo.images.json`
- `foo.manifest.json`

`foo.md`
- Main agent-readable text.
- Images appear as placeholders like `[[image:picture-p3-0]]`.

`foo.images.json`
- One entry per extracted picture.
- Includes `id`, `placeholder`, `page_no`, `bbox`, `mime_type`, and `base64`.

`foo.manifest.json`
- Includes `quality` (with nested `content_trust`), `selected_attempt`, and `ocr_remediation_applied`.
- Use this file to decide whether the result is safe to pass downstream.

## First Check
Read `foo.manifest.json` before consuming `foo.md`.

Example:

```bash
python3 -c 'import json, pathlib; p = pathlib.Path("PATH_TO_MANIFEST"); m = json.loads(p.read_text(encoding="utf-8")); print({"status": m["quality"]["status"], "agent_ready": m["quality"]["agent_ready"], "reasons": m["quality"]["reasons"], "selected_attempt": m["selected_attempt"], "ocr_remediation_applied": m["ocr_remediation_applied"]})'
```

Minimum fields to inspect:
- `manifest["quality"]["status"]`
- `manifest["quality"]["reasons"]`
- `manifest["quality"]["content_trust"]`
- `manifest["selected_attempt"]`

## Decision Flow
1. Resolve the input PDF path and an explicit output directory.
2. Run the extractor.
3. Read `*.manifest.json` before trusting `*.md`.
4. Decide from `manifest["quality"]["status"]`:
   - `good`: use `*.md` as the primary text artifact.
   - `salvaged`: use `*.md`, but treat it as OCR-remediated and lower confidence.
   - `failed_for_agent`: do not present it as clean ingestion; report the failure and the manifest reasons.
5. Check `manifest["selected_attempt"]` to see which attempt won. A remediation attempt can still end as `failed_for_agent`.
6. If image analysis matters, resolve placeholders through `*.images.json`.

## Images
When analysis depends on a specific figure or chart:
1. Find the placeholder in `.md`, for example `[[image:picture-p2-1]]`.
2. Look up the matching entry in `*.images.json` by `id` or `placeholder`.
3. Pass the corresponding base64 image through the current runtime's supported multimodal input path.

Example listing command:

```bash
python3 -c 'import json, pathlib; imgs = json.loads(pathlib.Path("PATH_TO_IMAGES_JSON").read_text(encoding="utf-8")); [print({"placeholder": img["placeholder"], "page_no": img["page_no"], "base64_len": len(img["base64"])}) for img in imgs]'
```

## Examples
Basic conversion:

```bash
conda run -n docling python -m docling_skill.cli \
  "/Users/rael/Documents/papers/2510.12399v2.pdf" \
  "/tmp/vibe-paper-sidecar"
```

Chinese OCR with explicit language and output path:

```bash
conda run -n docling python -m docling_skill.cli \
  "/Users/rael/Documents/papers/AI技术分享：门童与厨子模式.pdf" \
  "/tmp/openclaw-cn-sidecar" \
  --ocr-engine tesseract \
  --ocr-lang chi_sim
```

## Success Signal
- The command exits with code `0`.
- The output directory contains `foo.md`, `foo.images.json`, and `foo.manifest.json`.
- `foo.manifest.json` has been checked explicitly before using `foo.md`.

## Common Mistakes
- Do not skip the manifest check.
- Do not assume `selected_attempt` or a remediation attempt means the result is usable.
- Do not treat `failed_for_agent` as clean ingestion; it can still contain a small readable preview.
- Do not embed image base64 into Markdown manually; this tool already writes `*.images.json`.
- Do not rely on the default output directory unless the user explicitly accepted it.
