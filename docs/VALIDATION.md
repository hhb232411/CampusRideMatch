# Final clean-copy validation

Verified on 10 November 2026 in a new project copy and a new Python 3.12.2 virtual environment with **system-site-packages disabled**. The original business database was not used. This file summarizes executed checks; full logs accompany the separate final delivery under `Validation/`.

| Check | Observed result |
|---|---|
| Dependency installation | requirements.txt installed successfully; Flask 3.1.3; pip check passed |
| Fresh initialization | `flask --app app init-db --with-seed` created 20 fictional trips |
| Compatibility migration | migrate-db completed; schema version 2 |
| Structural / foreign-key check | integrity_check = ok; foreign_key_check = empty |
| Business audit | All 13 violation counts zero |
| Automated suite | **34/34 passed in 15.361 seconds**, process exit code 0 |
| Teaching SQL | All eight SELECT statements executed; result counts 1, 1, 3, 2, 3, 10, 4, 9 on the fresh seed |
| Browser | Real Edge 157.0.4341.42, headless, 1440×900; 11 page visits and login/logout forms passed; no JavaScript page errors |
| Evaluation CLI | Benchmark and generator help commands succeeded; five evaluation regression tests passed |
| Charting tool | requirements-evaluation.txt installed; both existing CSV runs were recomputed/verified and rendered to a temporary output directory |
| Video handoff integration | Supplied folder copied into the clean project; initialization and nine main-flow browser checkpoints passed; reset while running refused, reset after stop succeeded |

No full performance experiment was rerun. The 88 timings emitted by one existing automated test are a small isolated test fixture; the two original Stage 2 runs remain **31,680 records** and are unchanged. The report retains its explicitly labelled Stage 2 test duration (14.214 seconds); the duration above is the new Stage 5 execution, not a correction to that historical result.

The delivered application, schema, seed, tests, sample SQL and evaluation code are byte-identical to the working project at the start of Stage 5. Packaging changes consist of a concise README, stronger ignore rules and delivery/validation notes. The supporting database-design document clarifies SQLite type affinity, expiry and audit boundaries.

Verified limitations: only the stated Windows/Python/Edge environment was exercised here. Other Python versions, operating systems, browser engines, deployment capacity and actual video encoding/upload were not verified. GitHub publication, team details and final video remain pending; see [DELIVERABLES.md](DELIVERABLES.md).
