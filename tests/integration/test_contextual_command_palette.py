"""Integration coverage for session-aware command-palette actions."""

from dataclasses import replace
from pathlib import Path

from textual.command import CommandList, CommandPalette
from textual.pilot import Pilot
from textual.widgets import Input

from agenthub.app import AgentHubApp
from agenthub.harnesses import AgentHarness
from agenthub.native_sessions import LaunchSpec, NativeSession, NativeSessionService
from agenthub.presentation import SessionSidebar
from agenthub.presentation.modals import SessionDeleteConfirmationModal, SessionLinkModal
from agenthub.sessions import SessionKind


class PaletteAdapter:
    """Deterministic native provider for contextual palette workflows."""

    def __init__(
        self,
        harness: AgentHarness,
        native_session: NativeSession,
        *,
        supports_delete: bool,
    ) -> None:
        self.harness_id = harness.id
        self.supports_delete = supports_delete
        self._harness = harness
        self._native_sessions = (native_session,)
        self.resumed_ids: list[str] = []
        self.deleted_ids: list[str] = []

    def discover(self) -> tuple[NativeSession, ...]:
        return self._native_sessions

    async def resume(self, session: NativeSession) -> LaunchSpec:
        self.resumed_ids.append(session.native_session_id)
        assert session.cwd is not None
        return LaunchSpec(self._harness.command, session.cwd)

    async def delete(self, session: NativeSession) -> None:
        self.deleted_ids.append(session.native_session_id)
        self._native_sessions = tuple(
            candidate
            for candidate in self._native_sessions
            if candidate.native_session_id != session.native_session_id
        )


def _palette_titles(app: AgentHubApp) -> list[str]:
    command_list = app.screen.query_one(CommandList)
    return [str(option.prompt).splitlines()[0] for option in command_list.options]


async def _search_palette(
    app: AgentHubApp,
    pilot: Pilot[None],
    query: str,
) -> None:
    app.screen.query_one(Input).value = query
    await app.workers.wait_for_complete()
    await pilot.pause()


async def test_sidebar_focus_keeps_palette_context_on_the_active_session(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        native_session_service=NativeSessionService({}),
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
            "native-link-target",
            "Auth Refactor",
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
        sidebar = app.query_one(SessionSidebar)
        sidebar.move_cursor_to_session(pending.id)
        sidebar.focus_sidebar()

        await pilot.press("ctrl+p")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert isinstance(app.screen, CommandPalette)

        await _search_palette(app, pilot, 'Link "Active Agent"')

        assert 'Link "Active Agent"' in _palette_titles(app)
        assert 'Link "New session"' not in _palette_titles(app)

        await pilot.press("enter")
        await pilot.pause()

        assert isinstance(app.screen, SessionLinkModal)
        await pilot.press("enter")
        await pilot.pause()

        assert pending.native_session_id is None
        assert active.native_session_id == "native-link-target"
        assert candidate not in app.session_manager.sessions
        assert app.session_manager.active_session is active


async def test_unloaded_agent_uses_open_session_instead_of_contextual_resume(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    native = NativeSession(
        sleeping_harness.id,
        "native-resume",
        "Auth Refactor",
        tmp_path,
    )
    adapter = PaletteAdapter(
        sleeping_harness,
        native,
        supports_delete=False,
    )
    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        native_session_service=NativeSessionService({sleeping_harness.id: adapter}),
    )

    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        session = app.session_manager.sessions[0]

        await pilot.press("ctrl+s", "right", "ctrl+p")
        await app.workers.wait_for_complete()
        await pilot.pause()

        titles = _palette_titles(app)
        assert "Open Session" in titles
        assert not any(
            title.startswith(("Resume ", "Link ", "Delete ")) for title in titles
        )
        assert adapter.resumed_ids == []
        assert app.session_manager.active_session is None
        assert session.terminal is None


async def test_palette_uses_the_active_terminal_as_delete_target(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    native = NativeSession(
        sleeping_harness.id,
        "native-delete",
        "Delete Target",
        tmp_path,
    )
    adapter = PaletteAdapter(
        sleeping_harness,
        native,
        supports_delete=True,
    )
    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        native_session_service=NativeSessionService({sleeping_harness.id: adapter}),
    )

    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        session = app.session_manager.sessions[0]
        await app.activate_session(session.id)
        await pilot.pause()
        assert session.terminal is not None and session.terminal.has_focus

        await pilot.press("ctrl+p")
        await app.workers.wait_for_complete()
        await _search_palette(app, pilot, 'Delete "Delete Target"')

        assert 'Delete "Delete Target"' in _palette_titles(app)
        await pilot.press("enter")
        await pilot.pause()

        assert isinstance(app.screen, SessionDeleteConfirmationModal)


async def test_palette_delete_shows_guidance_for_unsupported_provider(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    antigravity = replace(
        sleeping_harness,
        id="antigravity",
        display_name="Antigravity",
    )
    native = NativeSession(
        antigravity.id,
        "native-antigravity",
        "Antigravity Session",
        tmp_path,
    )
    adapter = PaletteAdapter(
        antigravity,
        native,
        supports_delete=False,
    )
    app = AgentHubApp(
        agent_harnesses={antigravity.id: antigravity},
        native_session_service=NativeSessionService({antigravity.id: adapter}),
    )

    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        session = app.session_manager.sessions[0]
        await app.activate_session(session.id)
        await pilot.pause()

        await pilot.press("ctrl+p")
        await app.workers.wait_for_complete()
        await _search_palette(app, pilot, 'Delete "Antigravity Session"')
        assert 'Delete "Antigravity Session"' in _palette_titles(app)

        await pilot.press("enter")
        await pilot.pause()

        notification = list(app._notifications)[-1]
        assert notification.title == "Native deletion unavailable"
        assert notification.severity == "warning"
        assert "Antigravity does not currently expose" in notification.message
        assert not isinstance(app.screen, SessionDeleteConfirmationModal)
        assert adapter.deleted_ids == []


async def test_delete_callback_revalidates_a_removed_captured_session(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    native = NativeSession(
        sleeping_harness.id,
        "native-stale",
        "Stale Target",
        tmp_path,
    )
    adapter = PaletteAdapter(
        sleeping_harness,
        native,
        supports_delete=True,
    )
    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        native_session_service=NativeSessionService({sleeping_harness.id: adapter}),
    )

    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        session = app.session_manager.sessions[0]
        await app.activate_session(session.id)
        await pilot.pause()

        await pilot.press("ctrl+p")
        await app.workers.wait_for_complete()
        await _search_palette(app, pilot, 'Delete "Stale Target"')
        assert 'Delete "Stale Target"' in _palette_titles(app)

        app.session_manager.remove(session.id)
        await pilot.press("enter")
        await pilot.pause()

        notification = list(app._notifications)[-1]
        assert notification.message == (
            "The selected Agent session is no longer available."
        )
        assert notification.severity == "warning"
        assert adapter.deleted_ids == []
        assert not isinstance(app.screen, SessionDeleteConfirmationModal)


async def test_shell_sidebar_focus_keeps_the_active_agent_context(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        shell_harness=sleeping_harness,
        native_session_service=NativeSessionService({}),
    )
    active = app.session_manager.create(
        name="Fresh Agent",
        kind=SessionKind.AGENT,
        cwd=tmp_path,
        harness=sleeping_harness,
    )
    app.session_manager.add_discovered(
        native_session=NativeSession(
            sleeping_harness.id,
            "native-link-target",
            "Link Target",
            tmp_path,
        ),
        harness=sleeping_harness,
    )
    app.session_manager.create(
        name="Shell",
        kind=SessionKind.SHELL,
        cwd=tmp_path,
        harness=sleeping_harness,
    )
    app.session_manager.select(active.id)

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+s", "ctrl+p")
        await app.workers.wait_for_complete()
        await pilot.pause()

        titles = _palette_titles(app)
        assert 'Link "Fresh Agent"' in titles
        assert 'Link "Shell"' not in titles


async def test_active_shell_has_no_contextual_lifecycle_commands(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    app = AgentHubApp(
        shell_harness=sleeping_harness,
        native_session_service=NativeSessionService({}),
    )
    shell = app.session_manager.create(
        name="Shell",
        kind=SessionKind.SHELL,
        cwd=tmp_path,
        harness=sleeping_harness,
    )

    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.session_manager.active_session is shell

        await pilot.press("ctrl+p")
        await app.workers.wait_for_complete()
        await pilot.pause()

        titles = _palette_titles(app)
        assert not any(title.startswith(("Link ", "Delete ")) for title in titles)


async def test_home_palette_has_no_contextual_session_commands() -> None:
    app = AgentHubApp(native_session_service=NativeSessionService({}))

    async with app.run_test() as pilot:
        await pilot.press("ctrl+p")
        await app.workers.wait_for_complete()
        await pilot.pause()

        titles = _palette_titles(app)
        assert not any(
            title.startswith(("Link ", "Delete ")) for title in titles
        )
