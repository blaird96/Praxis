"""Textual application entry for Praxis."""

from __future__ import annotations

from textual.app import App
from textual.binding import Binding

from praxis.registry import bootstrap_registry
from praxis.ui.screens.home import initial_screen


class PraxisApp(App[None]):
    """Thin TUI over Praxis runner/domain logic."""

    TITLE = "Praxis"
    CSS = """
    Screen {
        layout: vertical;
    }

    #session-layout, #home-layout {
        height: 1fr;
        padding: 1 2;
    }

    .panel {
        margin-bottom: 1;
        padding: 0 1;
        border: tall $surface;
    }

    #objectives-scroll {
        height: 1fr;
        border: tall $surface;
        padding: 0 1;
    }

    #actions {
        height: auto;
        margin: 1 0;
    }

    #actions Button {
        margin-right: 1;
    }

    #status-log {
        height: 6;
        border: tall $surface;
    }

    #scenario-list {
        height: 8;
        margin: 1 0;
        border: tall $surface;
    }

    #home-status {
        margin: 1 0;
        height: 2;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=False),
    ]

    def on_mount(self) -> None:
        bootstrap_registry()
        self.push_screen(initial_screen())


def run_ui() -> None:
    """Launch the Praxis Textual application."""
    PraxisApp().run()
