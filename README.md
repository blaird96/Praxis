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

### Local web app (Milestone 4)

```bash
cd frontend && npm install && npm run build && cd ..
uv sync
uv run praxis app
```

Capability token stays in the URL fragment (`#token=…`) for REST. The embedded terminal uses a short-lived, single-use ticket from `POST /api/terminal/ticket` and connects to `ws://…/ws/terminal?ticket=…` (never puts the capability token in the WebSocket URL).

Workbench: file tree + Monaco + objectives + xterm.js over a real PTY/ConPTY shell in the exercise repo.

Dev with Vite HMR:

```bash
uv run praxis app --dev
# other terminal:
cd frontend && npm run dev
```

Training workspaces are created under `~/.praxis/` (override with `PRAXIS_HOME`).

`praxis ui` (Textual) is deprecated in favor of `praxis app`.
