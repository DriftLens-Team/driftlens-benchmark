# DriftLens Benchmark

English | [한국어](README.ko.md)

**Detect changes in business meaning from SQL-agent answers and queries.**

C03 changes the “large order” threshold from 2,000 to 3,000 cents while a paired control keeps 2,000 cents. Correct calculations can reflect a changed definition; changing counts can also reflect unchanged definitions.

The pipeline generates a SQLite database, runs an external SQL agent, validates its answers and queries, and scores drift predictions. It currently supports C03 and the L3 observation format.

SemAlign also supports **seven metrics, L0–L3, private generation validation, LOG/T1 and online T2 evaluation**. `run-semalign`, `detect-semalign`, and `evaluate-semalign` connect an external agent/v2 while keeping generation failures, abstentions and incomplete runs visible. See [runtime and acceptance instructions](docs/semalign-runtime.md), [input contracts](docs/semalign-data.md), and [initial verification records](docs/semalign-verification.md). Default `structural` validation shares the detector's semantic extractor; opt-in `behavioral` validation uses independent finite-case agreement. Neither establishes general SQL equivalence or generalization accuracy.

## Quick start

Python 3.11+ and Git are required. Run these PowerShell commands from the repository root. The first run uses the companion agent's fake model without credentials.

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]"
.venv/Scripts/python.exe -m pip install "driftlens-sql-agent @ git+https://github.com/DriftLens-Team/driftlens-sql-agent.git@b67ec9cd8c62763ec68ca896aafeef674081c558"
.venv/Scripts/python.exe -m driftlens_benchmark validate --suite benchmarks/suites/smoke.yaml
.venv/Scripts/python.exe -m driftlens_benchmark run --config configs/runs/smoke.yaml --out runs/demo
.venv/Scripts/python.exe -m driftlens_benchmark detect --public runs/demo/public/L3 --detector sql-rules --out runs/demo/predictions/sql-rules.jsonl
.venv/Scripts/python.exe -m driftlens_benchmark evaluate --run runs/demo --predictions runs/demo/predictions/sql-rules.jsonl
```

On Linux/macOS use `.venv/bin/python`. An activated environment also exposes `driftlens-benchmark`. See [contributing](CONTRIBUTING.md) for lockfile-based installation.

Use a new `--out` directory for each run. See [agent integration](docs/connecting-an-agent.md) to connect another agent.

## Expected smoke results

Eight synthetic orders produce four observations across two weeks and two arms.

| Arm | 2025-W02 | 2025-W03 | Drift label |
| --- | --- | --- | --- |
| Changed definition | 3 | 2 | false → true |
| Fixed definition | 3 | 4 | false → false |

The `sql-rules` baseline should produce TP=1, TN=3, FP=0, FN=0 with the fake provider. These results verify the integration pipeline; live LLM performance is not measured. A `no-drift` baseline is also available.

Reports appear under `runs/demo/reports/sql-rules/` as `report.md` and `metrics.json`. See [evaluation](docs/evaluation.md) for scoring and failure handling.

## Repository map

| Path | Responsibility |
| --- | --- |
| [benchmarks/](benchmarks/README.md) | Cases, definitions, reference SQL, questions and suites |
| [datasets/](datasets/README.md) | Provenance, schema, synthetic CSV and checksums |
| [configs/](configs/README.md) | Run and external agent selection |
| [src/driftlens_benchmark/](src/driftlens_benchmark/README.md) | Contracts, environment, adapters, observations, detectors and scoring |
| [tests/](tests/README.md) | Boundary, protocol and end-to-end checks |
| [examples/](examples/README.md) | External integration messages |
| [docs/](docs/README.md) | Usage, extensions, evaluation and migration |
| `runs/` | Generated DBs, truth, public observations, predictions and reports; ignored by Git |

## Scope

The agent receives a weekly snapshot and the current definition. Detectors read public observations and the baseline; the evaluator joins private labels.

Execution is local, without an OS sandbox. C03 SQL validation supports COUNT queries with date ranges and amount thresholds. For SemAlign aggregates, ratios, history and unsupported expressions, see [runtime instructions](docs/semalign-runtime.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and tests, [adding a case](docs/adding-a-case.md) for benchmark contributions, and [migration](docs/migration.md) for upgrading from the root scripts.

## License

[Apache-2.0](LICENSE) for code and included synthetic fixtures. External datasets retain their own licenses.
