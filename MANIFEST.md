# Output Manifest

## 2026-06-03 — A股 alpha discovery first cycle

- `alpha-stage/DATA_REPORT.md` — local data dictionary and data-risk report.
- `alpha-stage/artifacts/data_profile.json` — structured data profile.
- `alpha-stage/scripts/profile_data.py` — data profiling script.
- `alpha-stage/scripts/alpha_backtest.py` — daily alpha pilot/backtest script.
- `alpha-stage/IDEA_REPORT.md` — latest candidate result table.
- `alpha-stage/ALPHA_CANDIDATES.md` — candidate result table copy.
- `alpha-stage/artifacts/alpha_results.json` — structured A003/A005 post-fix 2025-2026 H5 results.
- `refine-logs/EXPERIMENT_PLAN.md` — experiment plan.
- `refine-logs/EXPERIMENT_TRACKER.md` — experiment status tracker.
- `refine-logs/EXPERIMENT_RESULTS.md` — experiment result pointer.
- `review-stage/AUTO_REVIEW.md` — Codex secondary reviewer report.
- `review-stage/REVIEW_STATE.json` — review state and promote/kill decisions.
- `ALPHA_DISCOVERY_LEDGER.md` — append-only alpha ledger.
- `NARRATIVE_REPORT.md` — narrative handoff report.
- `NARRATIVE_REPORT.html` — rendered HTML narrative with source SHA256.
- `RESULTS.md` — persistent results and validation conclusions.
- `DEBUG.md` — persistent debug/root-cause notes.

Validation evidence:

- `python alpha-stage/scripts/profile_data.py`
- `python -m py_compile alpha-stage/scripts/profile_data.py alpha-stage/scripts/alpha_backtest.py`
- `ALPHA_FAST=1 ALPHA_START=20250101 ALPHA_END=20260528 ALPHA_CANDIDATES=A003,A005 ALPHA_HORIZONS=5 python alpha-stage/scripts/alpha_backtest.py`
- Codex native secondary reviewer: gpt-5.5, xhigh, score 1/10, A003/A005 kill.
