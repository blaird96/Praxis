"""Typer CLI for Praxis."""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from praxis import runner
from praxis.errors import ExitCode, PraxisError
from praxis.models import Assignment, CheckResult

app = typer.Typer(
    name="praxis",
    help="Scenario-driven technical training.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    pretty_exceptions_show_locals=False,
)

console = Console(stderr=False)
error_console = Console(stderr=True)

DEBUG_ENV = "PRAXIS_DEBUG"


def _debug_enabled() -> bool:
    value = os.environ.get(DEBUG_ENV, "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _print_assignment(assignment: Assignment, repo_path: Path) -> None:
    console.print()
    console.print(f"[bold]{assignment.title}[/bold]")
    console.print()
    console.print(assignment.summary)
    if assignment.objectives:
        console.print()
        console.print("[bold]Objectives[/bold]")
        for item in assignment.objectives:
            console.print(f"  • {item}")
    console.print()
    resolved = repo_path.resolve()
    console.print(f"[bold]Exercise repository:[/bold] {resolved}")
    console.print(f"Enter the exercise with: [bold]cd {resolved}[/bold]")
    console.print("When finished, run: [bold]praxis check[/bold]")
    console.print()


def _print_check_result(result: CheckResult) -> None:
    table = Table(show_header=True, header_style="bold")
    table.add_column("Status", width=6)
    table.add_column("Objective")
    table.add_column("Detail")

    for objective in result.objectives:
        status = "[green]PASS[/green]" if objective.passed else "[red]FAIL[/red]"
        detail = objective.detail or ""
        table.add_row(status, objective.description, detail)

    console.print()
    console.print(table)
    console.print()
    if result.passed:
        console.print("[bold green]All objectives satisfied.[/bold green]")
    else:
        console.print(
            "[bold yellow]Not complete yet.[/bold yellow] "
            "Keep working in the exercise repo, then run "
            "[bold]praxis check[/bold] again."
        )
    console.print()


def _handle_praxis_error(exc: PraxisError) -> None:
    error_console.print(f"[red]Error:[/red] {exc.message}")
    raise typer.Exit(code=exc.exit_code) from None


def _handle_unexpected(exc: BaseException) -> None:
    if _debug_enabled():
        error_console.print(f"[red]Unexpected error:[/red] {exc}")
        traceback.print_exception(exc, file=sys.stderr)
        raise typer.Exit(code=ExitCode.ERROR) from exc
    error_console.print(
        f"[red]Error:[/red] Unexpected failure: {exc}. "
        f"Set {DEBUG_ENV}=1 for a traceback."
    )
    raise typer.Exit(code=ExitCode.ERROR) from None


@app.command("start")
def start_cmd(
    module: str = typer.Argument(..., help="Training module (e.g. git)."),
    scenario: str = typer.Option(
        ...,
        "--scenario",
        "-s",
        help="Scenario id within the module.",
    ),
) -> None:
    """Create a disposable workspace and start a scenario."""
    try:
        result = runner.start(module, scenario)
    except PraxisError as exc:
        _handle_praxis_error(exc)
    except Exception as exc:
        _handle_unexpected(exc)

    if result.previous_session_id:
        console.print(
            f"Previous session [cyan]{result.previous_session_id}[/cyan] retained."
        )
    console.print(
        f"[green]Started[/green] {result.session.module}/{result.session.scenario} "
        f"(session {result.session.session_id})"
    )
    _print_assignment(result.assignment, result.repo_path)


@app.command("check")
def check_cmd() -> None:
    """Validate the resolved session against its scenario objectives."""
    try:
        outcome = runner.check()
    except PraxisError as exc:
        _handle_praxis_error(exc)
    except Exception as exc:
        _handle_unexpected(exc)

    _print_check_result(outcome.result)
    raise typer.Exit(
        code=ExitCode.SUCCESS if outcome.result.passed else ExitCode.CHECK_FAILED
    )


@app.command("reset")
def reset_cmd() -> None:
    """Destroy and recreate only the exercise repo for the resolved session."""
    try:
        result = runner.reset()
    except PraxisError as exc:
        _handle_praxis_error(exc)
    except Exception as exc:
        _handle_unexpected(exc)

    console.print(
        "[yellow]Reset[/yellow] exercise repository "
        f"(session {result.session.session_id}). "
        "Only the disposable repo contents were replaced."
    )
    _print_assignment(result.assignment, result.repo_path)


@app.command("status")
def status_cmd() -> None:
    """Show the session resolved by hybrid discovery."""
    try:
        result = runner.status()
    except PraxisError as exc:
        _handle_praxis_error(exc)
    except Exception as exc:
        _handle_unexpected(exc)

    resolved = result.resolved
    session = resolved.session
    console.print()
    console.print(f"[bold]Session[/bold]     {session.session_id}")
    console.print(f"[bold]Module[/bold]      {session.module}")
    console.print(f"[bold]Scenario[/bold]    {session.scenario}")
    console.print(f"[bold]Status[/bold]      {session.status}")
    console.print(f"[bold]Workspace[/bold]   {Path(session.workspace_path).resolve()}")
    console.print(f"[bold]Repo[/bold]        {Path(session.repo_path).resolve()}")
    console.print(
        f"[bold]Active[/bold]      {'yes' if resolved.is_active else 'no'} "
        f"(resolved via {resolved.source})"
    )
    console.print()


@app.command("ui")
def ui_cmd() -> None:
    """Launch the interactive Praxis TUI (deprecated; use `praxis app`)."""
    console.print(
        "[yellow]Warning:[/yellow] `praxis ui` is deprecated and will be removed. "
        "Prefer [bold]praxis app[/bold] for the local web GUI."
    )
    try:
        from praxis.ui.app import run_ui

        run_ui()
    except PraxisError as exc:
        _handle_praxis_error(exc)
    except Exception as exc:
        _handle_unexpected(exc)


@app.command("app")
def app_cmd(
    host: str = typer.Option(
        "127.0.0.1",
        help="Bind address (localhost only).",
    ),
    port: int = typer.Option(8765, help="Local port."),
    open_browser: bool = typer.Option(
        True,
        "--open/--no-open",
        help="Open the default browser after start.",
    ),
    reload: bool = typer.Option(
        False,
        help="Dev auto-reload for the API process.",
    ),
    dev: bool = typer.Option(
        False,
        "--dev",
        help=(
            "Open the Vite dev origin (http://127.0.0.1:5173) with this launch's "
            "capability token. Run `npm run dev` in frontend/ separately."
        ),
    ),
) -> None:
    """Launch the local Praxis web application (API + UI)."""
    if host not in {"127.0.0.1", "localhost"}:
        error_console.print(
            "[red]Error:[/red] praxis app may only bind to 127.0.0.1 or localhost."
        )
        raise typer.Exit(code=ExitCode.ERROR)

    try:
        import webbrowser

        import uvicorn

        from praxis.api.app import app_public_url, vite_dev_url
        from praxis.api.security import AppSecurity
    except Exception as exc:
        _handle_unexpected(exc)

    bind_host = "127.0.0.1"
    security = AppSecurity.create(host=bind_host, port=port)
    os.environ["PRAXIS_APP_TOKEN"] = security.token
    os.environ["PRAXIS_APP_PORT"] = str(port)
    os.environ["PRAXIS_APP_HOST"] = bind_host

    console.print(f"[green]Praxis app[/green] listening on http://{bind_host}:{port}")
    console.print(
        "Capability token is placed in the URL fragment (#token=…) and held "
        "in browser memory only (local process authorization, not a user login)."
    )
    if open_browser:
        if dev:
            console.print(
                "[cyan]Dev mode:[/cyan] opening Vite origin. "
                "In another terminal: [bold]cd frontend && npm run dev[/bold]"
            )
            webbrowser.open(vite_dev_url(security))
        else:
            webbrowser.open(app_public_url(security))

    try:
        if reload:
            uvicorn.run(
                "praxis.api.asgi:app",
                host=bind_host,
                port=port,
                reload=True,
            )
        else:
            from praxis.api.asgi import build_app

            uvicorn.run(build_app(), host=bind_host, port=port, reload=False)
    except PraxisError as exc:
        _handle_praxis_error(exc)
    except Exception as exc:
        _handle_unexpected(exc)


def main() -> None:
    try:
        app()
    except PraxisError as exc:
        error_console.print(f"[red]Error:[/red] {exc.message}")
        sys.exit(exc.exit_code)
    except typer.Exit:
        raise
    except Exception as exc:
        if _debug_enabled():
            traceback.print_exception(exc, file=sys.stderr)
        else:
            error_console.print(
                f"[red]Error:[/red] Unexpected failure: {exc}. "
                f"Set {DEBUG_ENV}=1 for a traceback."
            )
        sys.exit(ExitCode.ERROR)


if __name__ == "__main__":
    main()
