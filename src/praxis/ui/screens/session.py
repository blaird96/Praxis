"""Session dashboard screen for an active Praxis exercise."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, RichLog, Static

from praxis import runner
from praxis.errors import PraxisError
from praxis.models import Assignment, CheckResult, Session
from praxis.ui.shell import ShellLaunchError, run_lab_shell


class SessionScreen(Screen[None]):
    """Show assignment, validation results, and lab actions."""

    BINDINGS = [
        ("c", "check", "Check"),
        ("e", "enter_shell", "Enter Lab Shell"),
        ("r", "reset", "Reset"),
        ("n", "new_exercise", "New Exercise"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, session: Session) -> None:
        super().__init__()
        self.session = session
        self.assignment: Assignment | None = None
        self.check_result: CheckResult | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="session-layout"):
            yield Static("", id="session-meta", classes="panel")
            yield Static("", id="assignment-panel", classes="panel")
            yield Static("", id="repo-panel", classes="panel")
            with VerticalScroll(id="objectives-scroll"):
                yield Static("", id="objectives-panel", classes="panel")
            with Horizontal(id="actions"):
                yield Button("Enter Lab Shell", id="btn-shell", variant="primary")
                yield Button("Check", id="btn-check")
                yield Button(
                    "Reset (destructive)",
                    id="btn-reset",
                    variant="warning",
                )
                yield Button("New Exercise", id="btn-new")
                yield Button("Quit", id="btn-quit")
            yield RichLog(id="status-log", max_lines=6, markup=True)
        yield Footer()

    def on_mount(self) -> None:
        # Windows cannot delete the exercise repo while it is this process's cwd.
        from praxis.workspace import ensure_cwd_outside

        ensure_cwd_outside(Path(self.session.repo_path))
        self._load_assignment()
        self._refresh_meta()
        self.run_check(announce=False)

    def _load_assignment(self) -> None:
        from praxis.registry import bootstrap_registry, get_scenario

        bootstrap_registry()
        scenario = get_scenario(self.session.module, self.session.scenario)
        self.assignment = scenario.assignment()
        self._refresh_assignment()

    def _refresh_meta(self) -> None:
        meta = self.query_one("#session-meta", Static)
        meta.update(
            f"[b]Praxis[/b]  ·  {self.session.module}/{self.session.scenario}\n"
            f"Session [cyan]{self.session.session_id}[/cyan]  ·  "
            f"status {self.session.status}"
        )
        repo = self.query_one("#repo-panel", Static)
        repo.update(
            f"[b]Exercise repository[/b]\n{Path(self.session.repo_path).resolve()}"
        )

    def _refresh_assignment(self) -> None:
        panel = self.query_one("#assignment-panel", Static)
        if self.assignment is None:
            panel.update("No assignment loaded.")
            return
        lines = [
            f"[b]{self.assignment.title}[/b]",
            "",
            self.assignment.summary,
        ]
        if self.assignment.objectives:
            lines.append("")
            lines.append("[b]Objectives[/b]")
            for item in self.assignment.objectives:
                lines.append(f"• {item}")
        panel.update("\n".join(lines))

    def _refresh_objectives(self) -> None:
        panel = self.query_one("#objectives-panel", Static)
        if self.check_result is None:
            panel.update("[dim]Run Check to see validation results.[/dim]")
            return
        lines = ["[b]Validation[/b]", ""]
        for objective in self.check_result.objectives:
            mark = "[green]PASS[/green]" if objective.passed else "[red]FAIL[/red]"
            detail = f" — {objective.detail}" if objective.detail else ""
            lines.append(f"{mark}  {objective.description}{detail}")
        overall = (
            "[green]All objectives satisfied.[/green]"
            if self.check_result.passed
            else "[yellow]Not complete yet.[/yellow]"
        )
        lines.extend(["", overall])
        panel.update("\n".join(lines))

    def _log(self, message: str) -> None:
        self.query_one("#status-log", RichLog).write(message)

    def run_check(self, *, announce: bool = True) -> None:
        try:
            outcome = runner.check()
        except PraxisError as exc:
            self.check_result = None
            self._refresh_objectives()
            self._log(f"[red]Check error:[/red] {exc.message}")
            return
        self.session = outcome.session
        self.check_result = outcome.result
        self._refresh_meta()
        self._refresh_objectives()
        if announce:
            if outcome.result.passed:
                self._log("[green]Check complete — all objectives passed.[/green]")
            else:
                self._log("[yellow]Check complete — objectives still failing.[/yellow]")

    def action_check(self) -> None:
        self.run_check(announce=True)

    def action_reset(self) -> None:
        try:
            result = runner.reset()
        except PraxisError as exc:
            self._log(f"[red]Reset error:[/red] {exc.message}")
            return
        except Exception as exc:  # noqa: BLE001 — keep UI alive
            self._log(f"[red]Reset error:[/red] {exc}")
            return
        self.session = result.session
        self.assignment = result.assignment
        self._refresh_meta()
        self._refresh_assignment()
        self._log("[yellow]Reset[/yellow] replaced the disposable exercise repository.")
        self.run_check(announce=True)

    def action_enter_shell(self) -> None:
        repo = Path(self.session.repo_path)
        self._log(f"Opening lab shell in {repo.resolve()} …")
        try:
            with self.app.suspend():
                code = run_lab_shell(repo)
        except ShellLaunchError as exc:
            self._log(f"[red]Shell error:[/red] {exc.message}")
            return
        except Exception as exc:  # noqa: BLE001 — keep UI alive
            self._log(f"[red]Shell error:[/red] {exc}")
            return
        self._log(f"Lab shell exited (code {code}). Refreshing validation…")
        self.run_check(announce=True)

    def action_new_exercise(self) -> None:
        from praxis.ui.screens.home import HomeScreen

        self.app.switch_screen(HomeScreen())

    def action_quit(self) -> None:
        self.app.exit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "btn-shell":
            self.action_enter_shell()
        elif button_id == "btn-check":
            self.action_check()
        elif button_id == "btn-reset":
            self.action_reset()
        elif button_id == "btn-new":
            self.action_new_exercise()
        elif button_id == "btn-quit":
            self.action_quit()
