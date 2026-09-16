"""Integration coverage for discovery and lazy native-session resumption."""

from pathlib import Path

from agenthub.app import AgentHubApp
from agenthub.harnesses import AgentHarness
from agenthub.native_sessions import LaunchSpec, NativeSession
from agenthub.sessions import SessionState
from agenthub.ui import SessionSidebar


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

    async def discover(self) -> tuple[NativeSession, ...]:
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

        await app.activate_session(session.id)
        await pilot.pause()
        terminal = session.terminal
        process = terminal.board.process if terminal is not None else None

        assert adapter.resumed_ids == ["native-1"]
        assert terminal is not None
        assert terminal.is_process_running
        assert terminal.has_focus

        await app.activate_session(session.id)
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
