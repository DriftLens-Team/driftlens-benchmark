# Repository instructions

- Keep implementation, verification results and future features distinct in README/docs.
- Benchmark cases live in benchmarks; runtime logic lives in src/driftlens_benchmark.
- Never import companion agent internals. Use the versioned JSONL process boundary.
- Public inputs must be projected from private truth with nested allowlist validation.
- Keep definition drift, SQL correctness, answer correctness and numeric changes separate.
- Do not delete existing runs, external raw data or credentials during cleanup.
- Run the checks in CONTRIBUTING.md. Default tests must not call a live model.
- Implement only supported cases; do not add empty Python placeholders for planned features.
