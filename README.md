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

### Local web app (Milestone 3)

```bash
cd frontend && npm install && npm run build && cd ..
uv run praxis app
```

The browser opens with a one-shot capability token in the URL fragment (`#token=…`). The app reads it into memory and clears the hash; privileged API calls send `X-Praxis-Token`.

From the home catalog, start an exercise, edit repository text files in Monaco, Save, and Check. Git commands still need an external terminal until Milestone 4.

Editor reads/writes are capped at **1 MiB** of UTF-8 text per file (`MAX_EDITOR_BYTES` in the API filesystem helper).

Dev with Vite HMR (same per-launch token; Origin allowlist unchanged):

```bash
# terminal A — opens http://127.0.0.1:5173/#token=…
uv run praxis app --dev

# terminal B
cd frontend && npm run dev
```

Training workspaces are created under `~/.praxis/` (override with `PRAXIS_HOME`).

`praxis ui` (Textual) is deprecated in favor of `praxis app`.
