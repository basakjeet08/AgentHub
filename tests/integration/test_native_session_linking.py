"""Integration coverage for explicit fresh-runtime reconciliation."""

from pathlib import Path

from textual.widgets import ContentSwitcher, Label, OptionList

from agenthub.app import AgentHubApp
from agenthub.harnesses import AgentHarness
from agenthub.native_sessions import NativeSession
from agenthub.sessions import AgentSession, SessionKind
from agenthub.ui import SessionSidebar, SidebarTab
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


async def test_explicit_target_links_native_row_without_restarting_terminal(
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

        app._begin_native_session_link(pending.id)
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
        sidebar = app.query_one(SessionSidebar)
        assert sidebar.visible_session_ids == (pending.id,)
        assert sidebar.tab_counts[SidebarTab.UNLOADED] == 1

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


async def test_explicit_target_links_hidden_agent_without_activating_it(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        native_session_adapters={},
    )
    pending = app.session_manager.create(
        name="New session",
        kind=SessionKind.AGENT,
        cwd=tmp_path,
        harness=sleeping_harness,
    )
    candidate = app.session_manager.add_discovered(
        native_session=NativeSession(
            sleeping_harness.id,
            "native-hidden",
            "Hidden Agent Title",
            tmp_path,
        ),
        harness=sleeping_harness,
    )
    active = app.session_manager.create(
        name="Active Agent",
        kind=SessionKind.AGENT,
        cwd=tmp_path,
        harness=sleeping_harness,
    )

    async with app.run_test() as pilot:
        await pilot.pause()
        pending_terminal = pending.terminal
        active_terminal = active.terminal
        assert pending_terminal is not None
        assert active_terminal is not None
        pending_process = pending_terminal.board.process
        active_process = active_terminal.board.process
        switcher = app.query_one("#session-content", ContentSwitcher)

        await pilot.press("ctrl+s")
        await pilot.press("up")
        session_list = app.query_one("#sidebar-session-list", OptionList)
        assert session_list.has_focus
        assert session_list.get_option_at_index(session_list.highlighted).id == pending.id
        assert app.session_manager.active_session is active

        app._begin_native_session_link(pending.id)
        await pilot.pause()
        assert isinstance(app.screen, NativeSessionLinkModal)

        await pilot.press("enter")
        await pilot.pause()

        assert app.session_manager.sessions == (pending, active)
        assert candidate not in app.session_manager.sessions
        assert app.session_manager.active_session is active
        assert switcher.current == app._terminal_dom_id(active.id)
        assert active_terminal.display
        assert not pending_terminal.display
        assert active.terminal is active_terminal
        assert active_terminal.board.process is active_process
        assert pending.native_session_id == "native-hidden"
        assert pending.name == "Hidden Agent Title"
        assert pending.cwd == tmp_path.resolve()
        assert pending.terminal is pending_terminal
        assert pending_terminal.board.process is pending_process
        assert pending_terminal.is_process_running

        current_session_list = app.query_one("#sidebar-session-list", OptionList)
        assert current_session_list.has_focus
        assert current_session_list.highlighted is not None
        assert (
            current_session_list.get_option_at_index(current_session_list.highlighted).id
            == pending.id
        )


async def test_explicit_shell_target_never_falls_back_to_active_agent(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    app, pending, native = _app_with_pending_and_native_session(
        sleeping_harness,
        tmp_path,
        tmp_path,
    )
    shell = app.session_manager.create(
        name="Shell",
        kind=SessionKind.SHELL,
        cwd=tmp_path,
        harness=sleeping_harness,
    )
    app.session_manager.select(pending.id)

    async with app.run_test() as pilot:
        await pilot.pause()
        sidebar = app.query_one(SessionSidebar)
        sidebar.select_tab(SidebarTab.SHELLS, focus=False)
        await pilot.press("ctrl+s")
        session_list = app.query_one("#sidebar-session-list", OptionList)
        assert session_list.has_focus
        assert session_list.get_option_at_index(session_list.highlighted).id == shell.id

        app._begin_native_session_link(shell.id)
        await pilot.pause()

        assert not isinstance(app.screen, NativeSessionLinkModal)
        assert pending.native_session_id is None
        assert app.session_manager.sessions == (pending, native, shell)
        assert app.session_manager.active_session is pending
        assert list(app._notifications)[-1].message == (
            "The selected session is not an Agent and cannot be linked."
        )


async def test_ineligible_explicit_target_does_not_fall_back_to_active_agent(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    app, active, native = _app_with_pending_and_native_session(
        sleeping_harness,
        tmp_path,
        tmp_path,
    )
    ineligible = app.session_manager.create(
        name="Already linked",
        kind=SessionKind.AGENT,
        cwd=tmp_path,
        harness=sleeping_harness,
    )
    ineligible.native_session_id = "native-already-linked"
    app.session_manager.select(active.id)

    async with app.run_test() as pilot:
        await pilot.pause()
        app._begin_native_session_link(ineligible.id)
        await pilot.pause()

        assert not isinstance(app.screen, NativeSessionLinkModal)
        assert active.native_session_id is None
        assert native in app.session_manager.sessions
        assert app.session_manager.active_session is active
        assert list(app._notifications)[-1].message == (
            "Already linked is already linked to a native session."
        )


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

        app._begin_native_session_link(pending.id)
        await pilot.pause()
        assert isinstance(app.screen, NativeSessionLinkModal)

        await pilot.press("escape")
        await pilot.pause()

        assert app.session_manager.sessions == (pending, native)
        assert pending.native_session_id is None
        assert pending.name == "New session"
        assert pending.terminal is terminal
        assert app.session_manager.active_session is pending


async def test_explicit_ineligible_targets_do_not_open_link_picker(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    shell_app = AgentHubApp(
        shell_harness=sleeping_harness,
        native_session_adapters={},
    )
    shell = shell_app.session_manager.create(
        name="Shell",
        kind=SessionKind.SHELL,
        cwd=tmp_path,
        harness=sleeping_harness,
    )
    async with shell_app.run_test() as pilot:
        await pilot.pause()
        shell_app._begin_native_session_link(shell.id)
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
        linked_app._begin_native_session_link(linked.id)
        await pilot.pause()
        assert not isinstance(linked_app.screen, NativeSessionLinkModal)
