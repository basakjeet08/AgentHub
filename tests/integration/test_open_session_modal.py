"""Integration coverage for the unified Open Session picker."""

from dataclasses import replace
from pathlib import Path

from textual.command import CommandPalette
from textual.widgets import ContentSwitcher, Input, OptionList, Static

from agenthub.app import AgentHubApp
from agenthub.harnesses import AgentHarness
from agenthub.native_sessions import LaunchSpec, NativeSession
from agenthub.presentation.modals import SessionSelectionModal
from agenthub.sessions import SessionKind


class FakeResumeAdapter:
    """Discover and resume one deterministic native conversation."""

    supports_delete = False

    def __init__(
        self,
        harness: AgentHarness,
        native_session: NativeSession,
    ) -> None:
        self.harness_id = harness.id
        self._harness = harness
        self._native_session = native_session
        self.resumed_ids: list[str] = []

    def discover(self) -> tuple[NativeSession, ...]:
        return (self._native_session,)

    async def resume(self, session: NativeSession) -> LaunchSpec:
        self.resumed_ids.append(session.native_session_id)
        assert session.cwd is not None
        return LaunchSpec(self._harness.command, session.cwd)


async def test_open_session_palette_command_opens_the_picker(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    app = AgentHubApp(native_session_adapters={})
    app.session_manager.create(
        name="Palette Target",
        kind=SessionKind.AGENT,
        cwd=tmp_path,
        harness=sleeping_harness,
    )

    async with app.run_test() as pilot:
        await pilot.press("ctrl+p")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert isinstance(app.screen, CommandPalette)

        app.screen.query_one(Input).value = "Open Session"
        await app.workers.wait_for_complete()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        assert isinstance(app.screen, SessionSelectionModal)


async def test_open_session_picker_lists_and_switches_running_agents_and_shells(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    app = AgentHubApp(native_session_adapters={})
    agent = app.session_manager.create(
        name="Auth Refactor",
        kind=SessionKind.AGENT,
        cwd=tmp_path,
        harness=sleeping_harness,
    )
    shell = app.session_manager.create(
        name="Backend Shell",
        kind=SessionKind.SHELL,
        cwd=tmp_path,
        harness=sleeping_harness,
    )

    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_open_session()
        await pilot.pause()

        assert isinstance(app.screen, SessionSelectionModal)
        session_list = app.screen.query_one("#session-selection-list", OptionList)
        assert app.screen.query_one("#session-selection-search", Input).has_focus
        assert tuple(
            (option.id, str(option.prompt)) for option in session_list.options
        ) == (
            (
                agent.id,
                "Auth Refactor",
            ),
            (
                shell.id,
                "Backend Shell",
            ),
        )

        await pilot.press("enter")
        await pilot.pause()

        assert app.session_manager.active_session is agent
        assert agent.terminal is not None and agent.terminal.has_focus
        assert app.query_one("#session-content", ContentSwitcher).current == (
            app._terminal_dom_id(agent.id)
        )

        app.action_open_session()
        await pilot.pause()
        await pilot.press("down", "enter")
        await pilot.pause()

        assert app.session_manager.active_session is shell
        assert shell.terminal is not None and shell.terminal.has_focus


async def test_open_session_picker_resumes_an_unloaded_native_agent(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    native_session = NativeSession(
        sleeping_harness.id,
        "native-open-session",
        "Existing Conversation",
        tmp_path,
    )
    adapter = FakeResumeAdapter(sleeping_harness, native_session)
    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        native_session_adapters={sleeping_harness.id: adapter},
    )

    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        (session,) = app.session_manager.sessions
        assert session.terminal is None

        app.action_open_session()
        await pilot.pause()
        session_list = app.screen.query_one("#session-selection-list", OptionList)
        assert tuple(
            (option.id, str(option.prompt)) for option in session_list.options
        ) == (
            (
                session.id,
                "Existing Conversation",
            ),
        )

        await pilot.press("enter")
        await pilot.pause()

        assert adapter.resumed_ids == ["native-open-session"]
        assert app.session_manager.active_session is session
        assert session.terminal is not None
        assert session.terminal.is_process_running
        assert session.terminal.has_focus


async def test_open_session_search_filters_by_harness_and_session_title(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    codex = replace(
        sleeping_harness,
        id="codex",
        display_name="Codex",
        icon="🌀",
    )
    devin = replace(
        sleeping_harness,
        id="devin",
        display_name="Devin",
        icon="🤖",
    )
    app = AgentHubApp(native_session_adapters={})
    codex_session = app.session_manager.add_discovered(
        native_session=NativeSession(
            codex.id,
            "native-codex",
            "Authentication Refactor",
            tmp_path,
        ),
        harness=codex,
    )
    devin_session = app.session_manager.add_discovered(
        native_session=NativeSession(
            devin.id,
            "native-devin",
            "API Cleanup",
            tmp_path,
        ),
        harness=devin,
    )

    async with app.run_test() as pilot:
        app.action_open_session()
        await pilot.pause()
        search = app.screen.query_one("#session-selection-search", Input)
        session_list = app.screen.query_one("#session-selection-list", OptionList)
        empty = app.screen.query_one("#session-selection-empty", Static)
        legend = app.screen.query_one("#session-selection-legend")

        assert tuple(str(option.prompt) for option in session_list.options) == (
            "🌀 Authentication Refactor",
            "🤖 API Cleanup",
        )
        assert tuple(str(item.content) for item in legend.query(Static)) == (
            "🌀 Codex",
            "🤖 Devin",
        )

        search.value = "CODEX"
        await pilot.pause()
        assert tuple(option.id for option in session_list.options) == (codex_session.id,)
        assert not empty.display

        search.value = "cleanup"
        await pilot.pause()
        assert tuple(option.id for option in session_list.options) == (devin_session.id,)
        assert not empty.display

        search.value = "missing"
        await pilot.pause()
        assert tuple(session_list.options) == ()
        assert empty.display


async def test_open_session_picker_escape_preserves_the_active_session(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    app = AgentHubApp(native_session_adapters={})
    active = app.session_manager.create(
        name="Active Agent",
        kind=SessionKind.AGENT,
        cwd=tmp_path,
        harness=sleeping_harness,
    )

    async with app.run_test() as pilot:
        app.action_open_session()
        await pilot.pause()
        assert isinstance(app.screen, SessionSelectionModal)

        await pilot.press("escape")
        await pilot.pause()

        assert not isinstance(app.screen, SessionSelectionModal)
        assert app.session_manager.active_session is active
        assert active.terminal is not None and active.terminal.has_focus


async def test_open_session_reports_when_no_sessions_are_available() -> None:
    app = AgentHubApp(native_session_adapters={})

    async with app.run_test() as pilot:
        app.action_open_session()
        await pilot.pause()

        assert not isinstance(app.screen, SessionSelectionModal)
        notification = list(app._notifications)[-1]
        assert notification.message == "No sessions are available to open."
        assert notification.severity == "information"


async def test_open_session_revalidates_a_removed_session(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    app = AgentHubApp(native_session_adapters={})
    session = app.session_manager.add_discovered(
        native_session=NativeSession(
            sleeping_harness.id,
            "native-removed",
            "Removed Conversation",
            tmp_path,
        ),
        harness=sleeping_harness,
    )

    async with app.run_test() as pilot:
        app.action_open_session()
        await pilot.pause()
        assert isinstance(app.screen, SessionSelectionModal)

        app.session_manager.remove(session.id)
        await pilot.press("enter")
        await pilot.pause()

        assert not isinstance(app.screen, SessionSelectionModal)
        notification = list(app._notifications)[-1]
        assert notification.message == "The selected session is no longer available."
        assert notification.severity == "warning"


async def test_locking_dismisses_open_session_and_refocuses_the_terminal(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    app = AgentHubApp(native_session_adapters={})
    active = app.session_manager.create(
        name="Active Agent",
        kind=SessionKind.AGENT,
        cwd=tmp_path,
        harness=sleeping_harness,
    )

    async with app.run_test() as pilot:
        app.action_open_session()
        await pilot.pause()
        assert isinstance(app.screen, SessionSelectionModal)

        await pilot.press("ctrl+g")
        await pilot.pause()

        assert app.hub_locked
        assert not isinstance(app.screen, SessionSelectionModal)
        assert active.terminal is not None and active.terminal.has_focus
