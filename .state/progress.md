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
