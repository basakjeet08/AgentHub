"""Integration coverage for explicit fresh-runtime reconciliation."""

from pathlib import Path

from textual.widgets import Label, OptionList

from agenthub.app import AgentHubApp
from agenthub.harnesses import AgentHarness
from agenthub.native_sessions import NativeSession
from agenthub.sessions import AgentSession, SessionKind
from agenthub.ui import SessionSidebar
from agenthub.ui.modals import NativeSessionLinkModal


def _app_with_pending_and_native_session(
    harness: AgentHarness,
    launch_cwd: Path,
    native_cwd: Path,
) -> tuple[AgentHubApp, AgentSession, AgentSession]:
    app = AgentHubApp(
        agent_harnesses={harness.id: harness},
        native_session_adapters={},
    )
    pending = app.session_manager.create(
        name="New session",
        kind=SessionKind.AGENT,
        cwd=launch_cwd,
        harness=harness,
    )
    native = app.session_manager.add_discovered(
        native_session=NativeSession(
            harness.id,
            "native-123456789",
            "Auth Refactor",
            native_cwd,
        ),
        harness=harness,
    )
    return app, pending, native


async def test_alt_m_links_selected_native_row_without_restarting_terminal(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    launch_cwd = tmp_path / "launch"
    other_cwd = tmp_path / "other"
    launch_cwd.mkdir()
    other_cwd.mkdir()
    app, pending, native = _app_with_pending_and_native_session(
        sleeping_harness,
        launch_cwd,
        launch_cwd,
    )
    irrelevant = app.session_manager.add_discovered(
        native_session=NativeSession(
            sleeping_harness.id,
            "native-other-directory",
            "Other Project Session",
            other_cwd,
        ),
        harness=sleeping_harness,
    )

    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        terminal = pending.terminal
        assert terminal is not None
        process = terminal.board.process

        await pilot.press("alt+m")
        await pilot.pause()

        assert isinstance(app.screen, NativeSessionLinkModal)
        assert app.screen.query_one("#native-session-link-title", Label).content == (
            f"Link {sleeping_harness.display_name} Session"
        )
        link_list = app.screen.query_one("#native-session-link-list", OptionList)
        assert len(link_list.options) == 1
        prompt = str(link_list.get_option(native.id).prompt)
        assert "Auth Refactor" in prompt
        assert str(launch_cwd) not in prompt
        assert "native-id" not in prompt

        await pilot.press("enter")
        await pilot.pause()

        assert app.session_manager.sessions == (pending, irrelevant)
        assert app.session_manager.active_session is pending
        assert pending.id != native.id
        assert pending.native_session_id == "native-123456789"
        assert pending.name == "Auth Refactor"
        assert pending.cwd == launch_cwd
        assert pending.terminal is terminal
        assert terminal.working_directory == launch_cwd
        assert terminal.board.process is process
        assert terminal.is_process_running
        assert terminal.has_focus
        assert app.query_one(SessionSidebar).visible_session_ids == (
            pending.id,
            irrelevant.id,
        )

        reconciled = app.session_manager.reconcile_discovered(
            native_sessions=(
                NativeSession(
                    sleeping_harness.id,
                    "native-123456789",
                    "Renamed by provider",
                    launch_cwd,
                ),
            ),
            harness=sleeping_harness,
        )
        app._refresh_sidebar()
        await pilot.pause()

        assert reconciled == (pending,)
        assert app.session_manager.sessions == (pending,)
        assert pending.name == "Renamed by provider"
        assert pending.terminal is terminal
        assert terminal.board.process is process


async def test_link_picker_escape_keeps_both_rows_unchanged(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    app, pending, native = _app_with_pending_and_native_session(
        sleeping_harness,
        tmp_path,
        tmp_path,
    )

    async with app.run_test() as pilot:
        await pilot.pause()
        terminal = pending.terminal

        await pilot.press("alt+m")
        await pilot.pause()
        assert isinstance(app.screen, NativeSessionLinkModal)

        await pilot.press("escape")
        await pilot.pause()

        assert app.session_manager.sessions == (pending, native)
        assert pending.native_session_id is None
        assert pending.name == "New session"
        assert pending.terminal is terminal
        assert app.session_manager.active_session is pending


async def test_alt_m_does_not_open_picker_for_home_shell_or_linked_agent(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    home_app = AgentHubApp(native_session_adapters={})
    async with home_app.run_test() as pilot:
        await pilot.press("alt+m")
        await pilot.pause()
        assert not isinstance(home_app.screen, NativeSessionLinkModal)

    shell_app = AgentHubApp(
        shell_harness=sleeping_harness,
        native_session_adapters={},
    )
    shell_app.session_manager.create(
        name="Shell",
        kind=SessionKind.SHELL,
        cwd=tmp_path,
        harness=sleeping_harness,
    )
    async with shell_app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("alt+m")
        await pilot.pause()
        assert not isinstance(shell_app.screen, NativeSessionLinkModal)

    linked_app, linked, native = _app_with_pending_and_native_session(
        sleeping_harness,
        tmp_path,
        tmp_path,
    )
    linked_app.session_manager.link_native_session(linked.id, native.id)
    async with linked_app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("alt+m")
        await pilot.pause()
        assert not isinstance(linked_app.screen, NativeSessionLinkModal)
