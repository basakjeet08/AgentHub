"""Unit tests for application orchestration and ownership."""

from agenthub.app import AgentHubApp
from agenthub.ui.bindings import (
    APPLICATION_BINDINGS,
    FOCUS_SIDEBAR_BINDING,
    FOCUS_WORKSPACE_BINDING,
    NEW_SESSION_BINDING,
    QUIT_BINDING,
)


def test_app_starts_empty_without_selecting_a_harness() -> None:
    app = AgentHubApp()

    assert app.session_manager.sessions == ()
    assert app.session_manager.active_session is None


def test_app_uses_the_agenthub_theme() -> None:
    app = AgentHubApp()

    assert app.theme == "tokyo-night"


def test_quit_binding_has_priority_over_terminal_input() -> None:
    assert AgentHubApp.BINDINGS == list(APPLICATION_BINDINGS)

    assert QUIT_BINDING.key == "ctrl+q"
    assert QUIT_BINDING.action == "quit"
    assert QUIT_BINDING.priority is True


def test_application_navigation_bindings_are_reserved() -> None:
    assert NEW_SESSION_BINDING.action == "new_session"
    assert FOCUS_SIDEBAR_BINDING.action == "focus_sidebar"
    assert FOCUS_WORKSPACE_BINDING.action == "focus_workspace"
    assert all(
        binding.priority
        for binding in (
            NEW_SESSION_BINDING,
            FOCUS_SIDEBAR_BINDING,
            FOCUS_WORKSPACE_BINDING,
        )
    )
