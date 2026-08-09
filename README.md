# Praxis

Locally running, scenario-driven technical training.

## Development

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --group dev
uv run pytest
uv run ruff check src tests
```

`uv` is a development/packaging tool only; Praxis does not require `uv` at runtime after install.

```bash
uv pip install -e .
praxis --help
```

Training workspaces are created under `~/.praxis/` (override with `PRAXIS_HOME`).
