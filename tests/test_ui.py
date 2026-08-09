"""Headless Textual UI tests."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pytest

from praxis import runner
from praxis.modules.git.scenarios.merge_conflict import GREETING_FILE
from praxis.registry import bootstrap_registry, clear_registry
from praxis.ui.app import PraxisApp
from praxis.ui.screens.home import HomeScreen
from praxis.ui.screens.session import SessionScreen
from praxis.ui.shell import ShellLaunchError


@pytest.fixture(autouse=True)
def _registry(praxis_home: Path) -> None:
    clear_registry()
    bootstrap_registry()
    yield
    clear_registry()


@pytest.mark.asyncio
async def test_ui_launches_home_with_no_session(praxis_home: Path) -> None:
    app = PraxisApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, HomeScreen)
        assert app.screen.query_one("#scenario-list")


@pytest.mark.asyncio
async def test_ui_loads_existing_active_session(praxis_home: Path) -> None:
    started = runner.start("git", "merge-conflict", home=praxis_home)
    app = PraxisApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, SessionScreen)
        assert app.screen.session.session_id == started.session.session_id
        assert app.screen.check_result is not None
        assert app.screen.check_result.passed is False
        by_id = {o.id: o.passed for o in app.screen.check_result.objectives}
        assert by_id["on-main"] is True
        assert by_id["no-markers"] is False
        assert by_id["no-unmerged"] is False


@pytest.mark.asyncio
async def test_ui_check_refreshes_validation(praxis_home: Path) -> None:
    runner.start("git", "merge-conflict", home=praxis_home)
    app = PraxisApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, SessionScreen)
        screen.check_result = None
        screen.action_check()
        await pilot.pause()
        assert screen.check_result is not None
        assert screen.check_result.passed is False


@pytest.mark.asyncio
async def test_ui_reset_refreshes_state(praxis_home: Path) -> None:
    started = runner.start("git", "merge-conflict", home=praxis_home)
    repo = Path(started.repo_path)
    (repo / GREETING_FILE).write_text("touched\n", encoding="utf-8")

    app = PraxisApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, SessionScreen)
        screen.action_reset()
        await pilot.pause()
        text = (repo / GREETING_FILE).read_text(encoding="utf-8")
        assert "<<<<<<<" in text
        assert screen.check_result is not None
        assert screen.check_result.passed is False


@pytest.mark.asyncio
async def test_ui_shell_return_triggers_check(
    praxis_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = runner.start("git", "merge-conflict", home=praxis_home)
    calls: list[Path] = []

    def fake_shell(repo_path: Path) -> int:
        calls.append(Path(repo_path).resolve())
        return 0

    @contextmanager
    def fake_suspend():
        yield

    monkeypatch.setattr("praxis.ui.screens.session.run_lab_shell", fake_shell)

    app = PraxisApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, SessionScreen)
        monkeypatch.setattr(app, "suspend", fake_suspend)
        screen.check_result = None
        screen.action_enter_shell()
        await pilot.pause()
        assert calls == [Path(started.repo_path).resolve()]
        assert screen.check_result is not None


@pytest.mark.asyncio
async def test_ui_shell_failure_does_not_crash(
    praxis_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner.start("git", "merge-conflict", home=praxis_home)

    def boom(_repo_path: Path) -> int:
        raise ShellLaunchError("shell unavailable")

    @contextmanager
    def fake_suspend():
        yield

    monkeypatch.setattr("praxis.ui.screens.session.run_lab_shell", boom)

    app = PraxisApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, SessionScreen)
        monkeypatch.setattr(app, "suspend", fake_suspend)
        screen.action_enter_shell()
        await pilot.pause()
        assert isinstance(app.screen, SessionScreen)
