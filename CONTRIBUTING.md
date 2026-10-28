# Contributing

Python 3.11+ is required. Install the editable package with `python -m pip install -e ".[dev]"`. For the pinned development dependency set, install uv and run:

```text
uv sync --frozen --extra dev
uv pip install "driftlens-sql-agent @ git+https://github.com/DriftLens-Team/driftlens-sql-agent.git@b67ec9cd8c62763ec68ca896aafeef674081c558"
```

Use the environment's Python for subsequent commands. On Windows it is `.venv/Scripts/python.exe`; on POSIX it is `.venv/bin/python`. A later `uv sync` may remove the separately installed companion, so reinstall it before its integration test.

```text
python -m pytest -q
python -m ruff check src tests examples
python -m build --wheel
```

Core tests use an independent protocol test double. The `companion` test calls the real, separately installed SQL-agent CLI with its fake provider. CI installs the pinned companion in a separate job. No live API credentials are used.

SemAlign uses a separate `semalign-companion` CI job pinned to agent commit `001b65b34f4475c6d90059539020d884be2b099f`. For local integration, set `DRIFTLENS_SEMALIGN_AGENT_PYTHON` to a v2 agent environment's Python and run `pytest -q -m semalign_companion`. The test creates its own data and calls the external CLI with the fake provider; it does not import agent internals. The old companion pin remains in the C03 job. See [SemAlign runtime](docs/semalign-runtime.md).

Cases require hand-calculated boundary expectations, reference SQL and a fixed-definition control. Preserve original case IDs. Contracts require positive/negative examples and compatibility notes. Generated databases, private labels, credentials and real run artifacts do not belong in Git.

Keep PR descriptions focused on changed behavior and verification. Document unsupported syntax and unverified live-model behavior. See [case contribution](docs/adding-a-case.md) and [architecture](docs/architecture.md).
