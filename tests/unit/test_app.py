"""Unit tests for application orchestration and ownership."""

from pathlib import Path

from agenthub.app import AgentHubApp
from agenthub.harnesses import AgentHarness


def test_app_creates_one_initial_session(
    sleeping_harness: AgentHarness,
) -> None:
    app = AgentHubApp(sleeping_harness)

    assert len(app.session_manager.sessions) == 1
    session = app.session_manager.active_session
    assert session is not None
    assert session.name == sleeping_harness.display_name
    assert session.cwd == Path.cwd()
    assert session.harness is sleeping_harness
    assert session.terminal.harness is sleeping_harness


def test_app_accepts_a_different_launch_directory(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    app = AgentHubApp(sleeping_harness, cwd=tmp_path)
    session = app.session_manager.active_session

    assert session is not None
    assert session.cwd == tmp_path.resolve()
    assert session.terminal.working_directory == tmp_path.resolve()


def test_quit_binding_has_priority_over_terminal_input() -> None:
    binding = next(binding for binding in AgentHubApp.BINDINGS if binding.action == "quit")

    assert binding.key == "ctrl+q"
    assert binding.action == "quit"
    assert binding.priority is True


def test_session_bindings_have_priority_over_terminal_input() -> None:
    bindings = {
        binding.key: binding
        for binding in AgentHubApp.BINDINGS
        if binding.key in {"ctrl+1", "ctrl+2"}
    }

    assert bindings["ctrl+1"].action == "select_session(0)"
    assert bindings["ctrl+2"].action == "select_session(1)"
    assert all(binding.priority for binding in bindings.values())
