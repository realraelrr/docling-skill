# Progress

## 2026-04-14

- Created isolated worktree at `/private/tmp/docling-skill-source-docling-json`
- Verified clean baseline with `conda run -n docling python -m pytest -q`
- Began Priority 1 execution for `source.docling.json`
- Added `source.docling.json` emission to the Python API and CLI output contract using the existing Docling conversion result
- Updated package tests, README, localized README, and skill docs for the new sidecar
- Fixed remediation-path JSON consistency and lazy structured-page export issues found during subagent review
- Re-verified the worktree with `env PYTHONPATH=/private/tmp/docling-skill-source-docling-json/src conda run -n docling python -m pytest -q` -> `29 passed in 3.92s`
- Advanced execution to Priority 2 (manifest artifact authority)
- Fixed the page-level PDF remediation path so merged `source.docling.json` is rebuilt from per-page Docling documents instead of reusing stale primary JSON
- Preserved original document identity in merged remediation JSON and made per-page Docling exports lazy outside the remediation path
- Added manifest artifact-authority fields for the `source.*` contract: `preferred_agent_artifact`, `authoritative_artifact`, and `available_artifacts`
- Normalized authority fields for final manifests and remediation attempts so salvaged outputs preserve the same downstream contract
- Documented the downstream rule explicitly: agents read `source.md` first, and systems recover or deepen from `source.docling.json`
- Added a builder-level regression test to pin `_build_attempt_manifest()` authority-field normalization and updated `SKILL.md` to include `available_artifacts` in the minimum manifest fields to inspect
- Committed the Priority 2 follow-up as `9e36f12` (`Add Priority 2 authority regression test`)
- Re-ran targeted verification with `env PYTHONPATH=/private/tmp/docling-skill-source-docling-json/src conda run -n docling python -m pytest tests/test_package_api.py tests/test_format_routing.py -q` -> `23 passed in 3.55s`
- Re-ran full verification with `env PYTHONPATH=/private/tmp/docling-skill-source-docling-json/src conda run -n docling python -m pytest -q` -> `30 passed in 3.00s`
- Closed Priority 2 after spec review and code-quality review; advanced execution to Priority 3 (text-native quality checks)
- Added Priority 3 text-native quality heuristics so DOCX/HTML/Markdown require surviving body structure instead of passing on any non-empty Markdown
- Added focused regression coverage for text-native structure survival, collapsed heading/list output, image-only output, and looser TXT expectations
- Re-ran the required targeted verification with `env PYTHONPATH=/private/tmp/docling-skill-source-docling-json/src conda run -n docling python -m pytest tests/test_quality_contract.py tests/test_text_native_quality.py tests/test_format_routing.py -q` -> `29 passed in 3.13s`
- Re-ran full verification with `env PYTHONPATH=/private/tmp/docling-skill-source-docling-json/src conda run -n docling python -m pytest -q` -> `37 passed in 3.43s`
- Added a Priority 3 follow-up regression for list-only `.txt` content so preserved plain-text lists like `- Buy milk` / `- Eggs` satisfy the looser TXT contract
- Relaxed the TXT branch in `_has_text_native_body_survival()` to accept surviving list structure alongside paragraph survival and short plain-text body content
- Verified RED with `env PYTHONPATH=/private/tmp/docling-skill-source-docling-json/src conda run -n docling python -m pytest tests/test_text_native_quality.py -q` -> `1 failed, 8 passed in 3.52s`
- Verified GREEN with `env PYTHONPATH=/private/tmp/docling-skill-source-docling-json/src conda run -n docling python -m pytest tests/test_text_native_quality.py -q` -> `9 passed in 3.36s`
- Re-ran the required targeted verification with `env PYTHONPATH=/private/tmp/docling-skill-source-docling-json/src conda run -n docling python -m pytest tests/test_quality_contract.py tests/test_text_native_quality.py tests/test_format_routing.py -q` -> `32 passed in 2.66s`
- Re-ran full verification with `env PYTHONPATH=/private/tmp/docling-skill-source-docling-json/src conda run -n docling python -m pytest -q` -> `40 passed in 2.73s`
- Added Priority 3 follow-up regressions for concise structured Markdown bodies so `# Note / Done` and `# 标题 / 摘要` are accepted while an overly thin body like `# Note / A` still fails
- Relaxed the structured text-native thresholds only when heading-plus-body structure survives, lowering the total/body character floor for concise real content without reopening non-empty-only acceptance
- Verified RED with `env PYTHONPATH=/private/tmp/docling-skill-source-docling-json/src conda run -n docling python -m pytest tests/test_text_native_quality.py -q` -> `2 failed, 10 passed in 3.12s`
- Verified GREEN with `env PYTHONPATH=/private/tmp/docling-skill-source-docling-json/src conda run -n docling python -m pytest tests/test_text_native_quality.py -q` -> `12 passed in 2.55s`
- Re-ran the required targeted verification with `env PYTHONPATH=/private/tmp/docling-skill-source-docling-json/src conda run -n docling python -m pytest tests/test_quality_contract.py tests/test_text_native_quality.py tests/test_format_routing.py -q` -> `35 passed in 2.66s`
- Re-ran full verification with `env PYTHONPATH=/private/tmp/docling-skill-source-docling-json/src conda run -n docling python -m pytest -q` -> `43 passed in 2.79s`
