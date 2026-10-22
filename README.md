# DriftLens Benchmark

English | [한국어](README.ko.md)

**Detect changes in business meaning from SQL-agent answers and queries.**

C03 changes the “large order” threshold from 2,000 to 3,000 cents while a paired control keeps 2,000 cents. Correct calculations can reflect a changed definition; changing counts can also reflect unchanged definitions.

Implemented: **C03 generation → external JSONL SQL agent → observation validation → public L3 bundle → detection → scoring**. The initial database has three columns. Six-table datasets, additional cases, L0–L2 and OS-isolated execution remain future work.

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

Outputs are never overwritten: use a new `--out` for each run. The agent can be installed anywhere; no sibling checkout or cross-repository imports are required. See [agent integration](docs/connecting-an-agent.md).

## Expected smoke results

Eight self-authored synthetic orders produce four observations across two weeks and two arms.

| Arm | 2025-W02 | 2025-W03 | Drift label |
| --- | --- | --- | --- |
| Changed definition | 3 | 2 | false → true |
| Fixed definition | 3 | 4 | false → false |

The SQL-rule baseline should produce TP=1, TN=3, FP=0, FN=0. This is a **fake-provider integration check**, not a claim about live LLM performance. A `no-drift` baseline is also available.

Reports appear under `runs/demo/reports/sql-rules/` as `report.md` and `metrics.json`. Generation errors, rejected/unverified observations and abstentions remain separate. Partial runs require explicit opt-in for scoring.

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

## Data boundaries

The agent receives a snapshot cut off at the reporting horizon and only its selected current definition. Public observations are projected from private truth using a nested allowlist. Detection reads the public bundle and baseline; evaluation joins private labels.

This is **local unisolated development execution**. Directory separation is not OS access control. The SQL recognizer supports a conservative COUNT/range/threshold subset and abstains outside it. See [evaluation rules](docs/evaluation.md).

## Test and contribute

```powershell
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check src tests examples
```

The companion integration test runs when its package is installed and explicitly skips otherwise. Default tests never call a live model. See [adding a case](docs/adding-a-case.md), [connecting an agent](docs/connecting-an-agent.md), and [migration](docs/migration.md).

## License

[Apache-2.0](LICENSE) for code and self-authored fixtures. Upstream Jaffle Shop CSVs are not redistributed. Their provenance and redistribution rights must be checked separately from this project's code license.
