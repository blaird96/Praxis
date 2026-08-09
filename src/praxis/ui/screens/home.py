"""Home screen for choosing / starting a scenario."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, ListItem, ListView, Static

from praxis import runner
from praxis.errors import PraxisError
from praxis.registry import bootstrap_registry, get_scenario, list_registered_scenarios
from praxis.session import load_active_session
from praxis.ui.screens.session import SessionScreen


class HomeScreen(Screen[None]):
    """List available scenarios when no session is active (or for New Exercise)."""

    BINDINGS = [
        ("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="home-layout"):
            yield Static("[b]Praxis[/b] — choose an exercise", id="home-title")
            yield Label("Available scenarios:")
            yield ListView(id="scenario-list")
            yield Static("", id="home-status")
            yield Button("Start selected", id="btn-start", variant="primary")
            yield Button("Quit", id="btn-quit")
        yield Footer()

    def on_mount(self) -> None:
        bootstrap_registry()
        list_view = self.query_one("#scenario-list", ListView)
        for module_id, scenario_id in list_registered_scenarios():
            scenario = get_scenario(module_id, scenario_id)
            label = f"{module_id}/{scenario_id} — {scenario.title}"
            list_view.append(ListItem(Label(label), name=f"{module_id}:{scenario_id}"))
        if list_view.children:
            list_view.index = 0

    def action_quit(self) -> None:
        self.app.exit()

    def _selected_pair(self) -> tuple[str, str] | None:
        list_view = self.query_one("#scenario-list", ListView)
        highlighted = list_view.highlighted_child
        if highlighted is None or highlighted.name is None:
            return None
        module_id, scenario_id = highlighted.name.split(":", 1)
        return module_id, scenario_id

    def _start_selected(self) -> None:
        pair = self._selected_pair()
        status = self.query_one("#home-status", Static)
        if pair is None:
            status.update("[red]Select a scenario first.[/red]")
            return
        module_id, scenario_id = pair
        try:
            result = runner.start(module_id, scenario_id)
        except PraxisError as exc:
            status.update(f"[red]{exc.message}[/red]")
            return
        self.app.switch_screen(SessionScreen(result.session))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-start":
            self._start_selected()
        elif event.button.id == "btn-quit":
            self.action_quit()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        del event
        self._start_selected()


def initial_screen() -> Screen[None]:
    """Open session dashboard when an active session exists; else home."""
    bootstrap_registry()
    active = load_active_session()
    if active is not None:
        return SessionScreen(active)
    return HomeScreen()
