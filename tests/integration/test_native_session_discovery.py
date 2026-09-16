"""Integration coverage for discovery and lazy native-session resumption."""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from textual.widgets import OptionList, Static

from agenthub.app import AgentHubApp
from agenthub.harnesses import AgentHarness
from agenthub.native_sessions import LaunchSpec, NativeSession
from agenthub.sessions import SessionState
from agenthub.ui import HomeScreen, SessionSidebar


class FakeNativeSessionAdapter:
    """Deterministic adapter used at the application boundary."""

    def __init__(
        self,
        harness: AgentHarness,
        cwd: Path,
        *,
        error: Exception | None = None,
        native_sessions: tuple[NativeSession, ...] | None = None,
    ) -> None:
        self.harness_id = harness.id
        self._harness = harness
        self._cwd = cwd
        self._error = error
        self._native_sessions = native_sessions
        self.resumed_ids: list[str] = []

    def discover(self) -> tuple[NativeSession, ...]:
        if self._error is not None:
            raise self._error
        if self._native_sessions is not None:
            return self._native_sessions
        return (
            NativeSession(self.harness_id, "native-1", "Existing session", self._cwd),
        )

    async def resume(self, session: NativeSession) -> LaunchSpec:
        self.resumed_ids.append(session.native_session_id)
        return LaunchSpec(self._harness.command, self._cwd)


async def test_discovered_session_starts_unloaded_and_resumes_once(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    adapter = FakeNativeSessionAdapter(sleeping_harness, tmp_path)
    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        native_session_adapters={sleeping_harness.id: adapter},
    )

    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        session = app.session_manager.sessions[0]

        assert session.native_session_id == "native-1"
        assert session.terminal is None
        assert session.state is SessionState.UNLOADED
        sidebar = app.query_one(SessionSidebar)
        assert sidebar.visible_session_ids == (session.id,)
        assert app.query_one(HomeScreen).query_one("#home-empty-copy", Static).content == (
            "Select a session from the sidebar\nor start a new coding-agent session."
        )
        assert app._discovery_executor is None

        await pilot.press("ctrl+a")
        await pilot.press("enter")
        await pilot.pause()
        terminal = session.terminal
        process = terminal.board.process if terminal is not None else None

        assert adapter.resumed_ids == ["native-1"]
        assert terminal is not None
        assert terminal.is_process_running
        assert terminal.has_focus

        await pilot.press("ctrl+a")
        await pilot.press("enter")
        await pilot.pause()

        assert session.terminal is terminal
        assert terminal.board.process is process
        assert adapter.resumed_ids == ["native-1"]

        notifications = list(app._notifications)
        assert [(item.title, item.message, item.severity, item.markup) for item in notifications] == [
            (
                "Session discovery",
                "Discovering sessions…",
                "information",
                False,
            ),
            (
                "Session discovery",
                f"Session discovery was successful. Sessions found:\n{sleeping_harness.display_name} - 1",
                "information",
                False,
            ),
        ]


async def test_provider_discovery_does_not_block_the_event_loop(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    class SlowAdapter(FakeNativeSessionAdapter):
        def discover(self) -> tuple[NativeSession, ...]:
            time.sleep(0.2)
            return ()

    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        native_session_adapters={},
    )
    adapter = SlowAdapter(sleeping_harness, tmp_path)
    executor = ThreadPoolExecutor(max_workers=1)
    started_at = time.monotonic()
    try:
        discovery = asyncio.create_task(app._discover_from_adapter(adapter, executor))
        await asyncio.sleep(0.02)

        assert time.monotonic() - started_at < 0.1
        assert not discovery.done()
        result = await discovery
    finally:
        executor.shutdown(wait=True, cancel_futures=True)

    assert result.sessions == ()
    assert result.error is None


async def test_resync_shortcut_reconciles_unloaded_native_sessions(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    adapter = FakeNativeSessionAdapter(sleeping_harness, tmp_path)
    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        native_session_adapters={sleeping_harness.id: adapter},
    )

    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        stale = app.session_manager.sessions[0]
        adapter._native_sessions = (
            NativeSession(
                sleeping_harness.id,
                "native-2",
                "New native session",
                tmp_path,
            ),
        )

        await pilot.press("ctrl+shift+r")
        await app.workers.wait_for_complete()
        await pilot.pause()

        sessions = app.session_manager.sessions
        assert stale not in sessions
        assert len(sessions) == 1
        assert sessions[0].native_session_id == "native-2"
        assert sessions[0].terminal is None
        assert app.query_one(SessionSidebar).visible_session_ids == (sessions[0].id,)

        retained = sessions[0]
        adapter._native_sessions = (
            NativeSession(
                sleeping_harness.id,
                "native-2",
                "Renamed native session",
                tmp_path,
            ),
        )
        await pilot.press("ctrl+shift+r")
        await app.workers.wait_for_complete()
        await pilot.pause()

        assert app.session_manager.sessions == (retained,)
        assert retained.name == "Renamed native session"
        prompt = app.query_one("#agent-session-list", OptionList).get_option(retained.id).prompt
        assert "Renamed native session" in str(prompt)
        assert [notification.message for notification in app._notifications][-2:] == [
            "Discovering sessions…",
            f"Session discovery was successful. Sessions found:\n{sleeping_harness.display_name} - 1",
        ]


async def test_provider_discovery_reports_when_no_sessions_are_found(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    adapter = FakeNativeSessionAdapter(
        sleeping_harness,
        tmp_path,
        native_sessions=(),
    )
    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        native_session_adapters={sleeping_harness.id: adapter},
    )

    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()

        notifications = list(app._notifications)
        assert [item.message for item in notifications] == [
            "Discovering sessions…",
            f"Session discovery was successful. Sessions found:\n{sleeping_harness.display_name} - 0",
        ]


async def test_discovery_completion_reports_all_configured_agents(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    second_harness = AgentHarness(
        id="second-agent",
        display_name="Second Agent",
        command=sleeping_harness.command,
        scroll=None,
    )
    adapters = {
        sleeping_harness.id: FakeNativeSessionAdapter(sleeping_harness, tmp_path),
        second_harness.id: FakeNativeSessionAdapter(second_harness, tmp_path),
    }
    app = AgentHubApp(
        agent_harnesses={
            sleeping_harness.id: sleeping_harness,
            second_harness.id: second_harness,
        },
        native_session_adapters=adapters,
    )

    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()

        notifications = list(app._notifications)
        assert [item.message for item in notifications] == [
            "Discovering sessions…",
            (
                f"Session discovery was successful. Sessions found:\n"
                f"{sleeping_harness.display_name} - 1\nSecond Agent - 1"
            ),
        ]


async def test_provider_discovery_failure_does_not_stop_application(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    adapter = FakeNativeSessionAdapter(
        sleeping_harness,
        tmp_path,
        error=RuntimeError("provider unavailable"),
    )
    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        native_session_adapters={sleeping_harness.id: adapter},
    )

    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()

        assert app.is_running
        assert app.session_manager.sessions == ()
        notifications = list(app._notifications)
        assert [
            (item.message, item.severity, item.markup) for item in notifications
        ] == [
            ("Discovering sessions…", "information", False),
            (
                (
                    f"Session discovery completed with errors:\n"
                    f"{sleeping_harness.display_name} - failed: provider unavailable"
                ),
                "warning",
                False,
            ),
        ]
