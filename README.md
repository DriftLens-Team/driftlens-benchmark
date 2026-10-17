# DriftLens benchmark v0.1

A reproducible benchmark for detecting semantic drift in SQL-based AI agent logs.


Scenario A only: large_orders changes from >= 2000 to >= 3000 integer cents.
Adapted from the existing 2026-10-16 generator prototype; the original files and
four tests were preserved. Python 3.11+, standard library only for execution.

## Run (PowerShell)
```powershell
python -m unittest -v
python generate.py --orders data/fixture_orders.csv --start 2025-01-06 --weeks 2 --out runs/demo
```
Expected template-only counts: 3 and 2. This is an eight-row synthetic fixture,
not full jaffle-shop, and template output is not LLM-generated benchmark data.
CSV and JSONL orders accept `id`, `ordered_at`, `order_total` (integer cents).
Timezone-aware timestamps normalize to UTC; naive inputs are assumed UTC.
The CLI conservatively requires the requested full weeks within the source date span.
Use a new output directory per run; existing results are never overwritten.

For genuine answer generation, set `UPSTAGE_API_KEY` externally and
`UPSTAGE_MODEL` to an account-supported model, then add `--mode llm`.
`--model` can override the model environment variable. No API calls were made
in this implementation session. Do not commit credentials or generated runs.
Fake HTTP responses test the transport contract, not provider compatibility or quality.

## Contract and isolation
`logs.jsonl` contains exactly ten flat top-level fields: log_id, timestamp,
agent_id, team, request, sql, answer_text, definition_note, reported_values,
referenced_concepts. reported_values is an array of concept_id/value/period objects.
`truth.jsonl` has log_id, ontology_version_used, drift_id, contaminated.
`run.private.json` records input SHA256, thresholds, effective date, model/mode,
UTC rules and success/failure counts. Failed answers go to
`failures.private.jsonl`, never silently corrected. The CLI exits 1 on generation failures.
`orders.sqlite` is a source-only SQL tool snapshot; it contains no labels or ontology.

Weeks are [Monday 00:00 UTC, next Monday 00:00 UTC), with Sunday 23:59:59
conversation timestamps. One version applies to the whole week, selected at that
timestamp. Change date starts at UTC midnight; Jan 15 makes 2025-W03 v2.
Pre-change truth is v1/null/false; post-change truth is v2/A/true.
Contaminated means changed relative to v1, not a computation error.

`public_logs.load_public` accepts only logs.jsonl with exact public keys and
strict nested value fields, rejecting private files, unexpected fields and duplicates.
Only L3 is implemented. Pass only public records to detector code; never mount
truth or run metadata into its environment. The reader is not an OS access control
or a proof that arbitrary text contains no semantic leakage.

reported_values always represents the executed SQL, not an independent current-policy
oracle. Stale-definition SQL observations are valid observations and must not be
filtered for differing from a current-policy count. The default Scenario A generator
follows the active version; stale SQL is exercised in the separate agent test.
The answer validator compares against that actual query result and checks numbers
and common leakage terms; semantic paraphrases still need human review.

## Provenance and limits
The implementation extends the original Scenario A prototype and its four tests.
The complete runnable v0.1 contract is documented above; no internal document
access is required. This repository provides reproducible inputs for semantic
drift detection research, not a completed detector or scoring system.

12 tests cover original behavior, JSONL equivalence, UTC/ISO year/week boundaries,
change-day inclusion, reproducibility, fake LLM responses, leakage rejection,
public/private boundary, stale SQL, and read-only SQL budgets.
Full jaffle-shop execution, live LLM/model access, change detection and scoring
are unverified or outside scope. Numeric extraction capability is not evaluated.


## 향후 구조 (문서·주석 전용)

[구조와 구현 상태](docs/README.md)에 폴더 역할과 설정 예시를 정리했다. 새 Python 파일은 주석만 있으며 신규 기능을 실행하지 않는다. 기존 실행 코드·테스트·import는 그대로다. 두 저장소를 JSONL 별도 프로세스로 연결하는 방식은 향후 목표이며, 현재 agent는 benchmark 유틸리티를 import하는 SQL replay다.
