"""Integration coverage for focus-scoped permanent native-session deletion."""

import sys
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

import pytest
from textual.widgets import Button, OptionList, Static

from agenthub.app import AgentHubApp
from agenthub.harnesses import AgentHarness
from agenthub.native_sessions import (
    LaunchSpec,
    NativeSession,
    NativeSessionDeletionUnavailableError,
)
from agenthub.sessions import SessionKind, SessionState
from agenthub.ui import SessionSidebar
from agenthub.ui.modals import NativeSessionDeleteModal


class DeletionAdapter:
    """Mutable native provider used to exercise app-owned deletion policy."""

    def __init__(
        self,
        harness: AgentHarness,
        cwd: Path,
        sessions: tuple[NativeSession, ...] = (),
    ) -> None:
        self.harness_id = harness.id
        self.harness = harness
        self.cwd = cwd
        self.sessions = sessions
        self.discover_calls = 0
        self.delete_calls: list[str] = []
        self.delete_error: Exception | None = None
        self.keep_after_delete = False
        self.on_delete: Callable[[], None] | None = None

    def discover(self) -> tuple[NativeSession, ...]:
        self.discover_calls += 1
        return self.sessions

    async def resume(self, session: NativeSession) -> LaunchSpec:
        return LaunchSpec(self.harness.command, self.cwd)

    async def delete(self, session: NativeSession) -> None:
        self.delete_calls.append(session.native_session_id)
        if self.on_delete is not None:
            self.on_delete()
        if self.delete_error is not None:
            raise self.delete_error
        if not self.keep_after_delete:
            self.sessions = tuple(
                candidate
                for candidate in self.sessions
                if candidate.native_session_id != session.native_session_id
            )


def _native(harness: AgentHarness, native_id: str, name: str, cwd: Path) -> NativeSession:
    return NativeSession(harness.id, native_id, name, cwd)


async def test_manual_native_deletion_is_reconciled_after_only_its_process_exits(
    tmp_path: Path,
) -> None:
    exiting = AgentHarness(
        id="exiting-provider",
        display_name="Exiting Provider",
        command=(sys.executable, "-c", "import time; time.sleep(0.2)"),
        scroll=None,
    )
    unrelated = AgentHarness(
        id="unrelated-provider",
        display_name="Unrelated Provider",
        command=(sys.executable, "-c", "import time; time.sleep(30)"),
        scroll=None,
    )
    exiting_adapter = DeletionAdapter(
        exiting,
        tmp_path,
        (_native(exiting, "native-exit", "Exit target", tmp_path),),
    )
    unrelated_adapter = DeletionAdapter(
        unrelated,
        tmp_path,
        (_native(unrelated, "native-other", "Other", tmp_path),),
    )
    app = AgentHubApp(
        agent_harnesses={exiting.id: exiting, unrelated.id: unrelated},
        native_session_adapters={
            exiting.id: exiting_adapter,
            unrelated.id: unrelated_adapter,
        },
    )

    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        target = next(
            session
            for session in app.session_manager.sessions
            if session.native_session_id == "native-exit"
        )
        await app.activate_session(target.id)
        exiting_adapter.sessions = ()

        for _ in range(30):
            if target not in app.session_manager.sessions:
                break
            await pilot.pause(0.05)

        assert target not in app.session_manager.sessions
        assert exiting_adapter.discover_calls == 2
        assert unrelated_adapter.discover_calls == 1


async def test_ctrl_d_deletes_highlighted_agent_not_active_agent(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    adapter = DeletionAdapter(
        sleeping_harness,
        tmp_path,
        (
            _native(sleeping_harness, "native-active", "Active Agent", tmp_path),
            _native(sleeping_harness, "native-highlighted", "Auth Refactor", tmp_path),
        ),
    )
    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        native_session_adapters={sleeping_harness.id: adapter},
    )

    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        active, highlighted = app.session_manager.sessions
        await app.activate_session(active.id)
        await pilot.pause()
        sidebar = app.query_one(SessionSidebar)
        sidebar.move_cursor_to_session(highlighted.id)
        sidebar.focus_agents()

        await pilot.press("ctrl+d")
        await pilot.pause()

        assert isinstance(app.screen, NativeSessionDeleteModal)
        assert 'Delete "Auth Refactor" permanently?' == str(
            app.screen.query_one("#native-session-delete-copy", Static).content
        )

        cancel = app.screen.query_one("#native-session-delete-cancel", Button)
        confirm = app.screen.query_one("#native-session-delete-confirm", Button)
        assert cancel.has_focus

        await pilot.press("right")
        assert confirm.has_focus
        await pilot.press("left")
        assert cancel.has_focus
        await pilot.press("down", "enter")
        for _ in range(20):
            if highlighted not in app.session_manager.sessions:
                break
            await pilot.pause(0.05)

        assert adapter.delete_calls == ["native-highlighted"]
        assert app.session_manager.sessions == (active,)
        assert app.session_manager.active_session is active
        assert active.terminal is not None
        assert active.terminal.is_process_running


async def test_ctrl_d_with_terminal_focus_reaches_native_terminal(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    adapter = DeletionAdapter(
        sleeping_harness,
        tmp_path,
        (_native(sleeping_harness, "native-1", "Native", tmp_path),),
    )
    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        native_session_adapters={sleeping_harness.id: adapter},
    )

    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        session = app.session_manager.sessions[0]
        await app.activate_session(session.id)
        await pilot.pause()
        assert session.terminal is not None
        pty = session.terminal.board.pty
        assert pty is not None

        with patch.object(pty, "write", wraps=pty.write) as write_spy:
            await pilot.press("ctrl+d")
            await pilot.pause()

        write_spy.assert_called_once_with("\x04")
        assert not isinstance(app.screen, NativeSessionDeleteModal)
        assert adapter.delete_calls == []


@pytest.mark.parametrize("cancel_with", ("escape", "button"))
async def test_cancel_native_deletion_leaves_everything_untouched(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
    cancel_with: str,
) -> None:
    adapter = DeletionAdapter(
        sleeping_harness,
        tmp_path,
        (_native(sleeping_harness, "native-1", "Keep Me", tmp_path),),
    )
    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        native_session_adapters={sleeping_harness.id: adapter},
    )

    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        session = app.session_manager.sessions[0]
        await pilot.press("ctrl+a", "ctrl+d")
        assert isinstance(app.screen, NativeSessionDeleteModal)

        if cancel_with == "escape":
            await pilot.press("escape")
        else:
            await pilot.click("#native-session-delete-cancel")
        await pilot.pause()

        assert app.session_manager.sessions == (session,)
        assert session.native_session_id == "native-1"
        assert session.state is SessionState.UNLOADED
        assert adapter.delete_calls == []


@pytest.mark.parametrize(
    ("failure_mode", "detail"),
    (
        ("provider", "provider refused deletion"),
        ("verification", "provider still reports the conversation"),
    ),
)
async def test_failed_native_deletion_preserves_row_and_native_identity(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
    failure_mode: str,
    detail: str,
) -> None:
    adapter = DeletionAdapter(
        sleeping_harness,
        tmp_path,
        (_native(sleeping_harness, "native-1", "Keep Me", tmp_path),),
    )
    if failure_mode == "provider":
        adapter.delete_error = RuntimeError(detail)
    else:
        adapter.keep_after_delete = True
    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        native_session_adapters={sleeping_harness.id: adapter},
    )

    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        session = app.session_manager.sessions[0]
        await pilot.press("ctrl+a", "ctrl+d")
        await pilot.click("#native-session-delete-confirm")
        for _ in range(20):
            if session.state is not SessionState.DELETING:
                break
            await pilot.pause(0.05)

        assert app.session_manager.sessions == (session,)
        assert session.native_session_id == "native-1"
        assert session.state is SessionState.UNLOADED
        assert detail in list(app._notifications)[-1].message
        assert list(app._notifications)[-1].severity == "error"


async def test_unavailable_native_deletion_shows_provider_guidance_as_warning(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    guidance = (
        "Antigravity does not currently expose programmatic conversation deletion.\n"
        "Delete it using Antigravity's /resume picker, then AgentHub will refresh "
        "automatically."
    )
    adapter = DeletionAdapter(
        sleeping_harness,
        tmp_path,
        (_native(sleeping_harness, "native-1", "Keep Me", tmp_path),),
    )
    adapter.delete_error = NativeSessionDeletionUnavailableError(guidance)
    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        native_session_adapters={sleeping_harness.id: adapter},
    )

    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        session = app.session_manager.sessions[0]
        await pilot.press("ctrl+a", "ctrl+d", "right", "enter")
        for _ in range(20):
            if session.state is not SessionState.DELETING:
                break
            await pilot.pause(0.05)

        notification = list(app._notifications)[-1]
        assert notification.message == guidance
        assert notification.title == "Native deletion unavailable"
        assert notification.severity == "warning"
        assert app.session_manager.sessions == (session,)
        assert session.native_session_id == "native-1"


async def test_running_native_agent_is_stopped_before_provider_deletion(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    adapter = DeletionAdapter(
        sleeping_harness,
        tmp_path,
        (_native(sleeping_harness, "native-1", "Running", tmp_path),),
    )
    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        native_session_adapters={sleeping_harness.id: adapter},
    )

    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        session = app.session_manager.sessions[0]
        await app.activate_session(session.id)
        await pilot.pause()
        terminal = session.terminal
        assert terminal is not None and terminal.is_process_running
        observed: list[tuple[object, bool]] = []
        adapter.on_delete = lambda: observed.append(
            (session.terminal, terminal.is_process_running)
        )

        await pilot.press("ctrl+a", "ctrl+d")
        await pilot.click("#native-session-delete-confirm")
        for _ in range(20):
            if session not in app.session_manager.sessions:
                break
            await pilot.pause(0.05)

        assert observed == [(None, False)]
        assert session not in app.session_manager.sessions
        assert app.session_manager.active_session is None


async def test_fresh_agent_warns_and_shell_focus_cannot_delete_natively(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    adapter = DeletionAdapter(sleeping_harness, tmp_path)
    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        shell_harness=sleeping_harness,
        native_session_adapters={sleeping_harness.id: adapter},
    )
    fresh = app.session_manager.create(
        name="New session",
        kind=SessionKind.AGENT,
        cwd=tmp_path,
        harness=sleeping_harness,
    )
    shell = app.session_manager.create(
        name="Shell",
        kind=SessionKind.SHELL,
        cwd=tmp_path,
        harness=sleeping_harness,
    )

    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        sidebar = app.query_one(SessionSidebar)
        sidebar.focus_agents()
        await pilot.press("ctrl+d")
        await pilot.pause()

        assert not isinstance(app.screen, NativeSessionDeleteModal)
        assert "Fresh Agents are not linked" in list(app._notifications)[-1].message

        sidebar.focus_shells()
        await pilot.pause()
        shell_list = app.query_one("#shell-session-list", OptionList)
        assert shell_list.has_focus
        await pilot.press("ctrl+d")
        await pilot.pause()

        assert app.session_manager.sessions == (fresh, shell)
        assert not isinstance(app.screen, NativeSessionDeleteModal)
        assert adapter.delete_calls == []
