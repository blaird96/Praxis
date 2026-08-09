"""CLI entrypoint (commands implemented in a later step)."""

from __future__ import annotations

import typer

app = typer.Typer(
    name="praxis",
    help="Scenario-driven technical training.",
    no_args_is_help=True,
)
