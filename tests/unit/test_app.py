"""Unit tests for application orchestration and ownership."""

from pathlib import Path

from agenthub.app import AgentHubApp
from agenthub.harnesses import AgentHarness
from agenthub.sessions import SessionKind
from agenthub.ui import SessionSidebar
from agenthub.ui.bindings import (
    APPLICATION_BINDINGS,
    COMMAND_PALETTE_BINDING,
    FOCUS_AGENTS_BINDING,
    FOCUS_SHELLS_BINDING,
    RESYNC_SESSIONS_BINDING,
    TERMINAL_GATED_ACTIONS,
    TOGGLE_HUB_LOCK_BINDING,
)


def test_app_starts_empty_without_selecting_a_harness() -> None:
    app = AgentHubApp()

    assert app.session_manager.sessions == ()
    assert app.session_manager.active_session is None
    assert app.hub_locked is False


def test_app_uses_the_agenthub_theme() -> None:
    app = AgentHubApp()

    assert app.theme == "tokyo-night"


def test_session_kind_partitions_agent_and_shell_sessions(
    sleeping_harness: AgentHarness,
) -> None:
    app = AgentHubApp()
    shell = app.session_manager.create(
        name="Shell session",
        kind=SessionKind.SHELL,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )

    assert app._agent_sessions() == ()
    assert app._shell_sessions() == (shell,)


def test_application_bindings_are_priority_candidates_for_keyboard_ownership() -> None:
    assert list(APPLICATION_BINDINGS) == AgentHubApp.BINDINGS

    assert TOGGLE_HUB_LOCK_BINDING.key == "ctrl+g"
    assert TOGGLE_HUB_LOCK_BINDING.action == "toggle_hub_lock"
    assert TOGGLE_HUB_LOCK_BINDING.priority is True


def test_application_navigation_bindings_are_reserved() -> None:
    assert FOCUS_AGENTS_BINDING.key == "ctrl+a"
    assert FOCUS_AGENTS_BINDING.action == "focus_agents"
    assert FOCUS_SHELLS_BINDING.key == "ctrl+s"
    assert FOCUS_SHELLS_BINDING.action == "focus_shells"
    assert all(
        binding.priority
        for binding in (
            FOCUS_AGENTS_BINDING,
            FOCUS_SHELLS_BINDING,
        )
    )
    assert COMMAND_PALETTE_BINDING.key == "ctrl+p"
    assert COMMAND_PALETTE_BINDING.action == "command_palette"
    assert COMMAND_PALETTE_BINDING.priority is True
    assert RESYNC_SESSIONS_BINDING.key == "ctrl+shift+r"
    assert RESYNC_SESSIONS_BINDING.action == "resync_sessions"
    assert RESYNC_SESSIONS_BINDING.priority is True
    assert RESYNC_SESSIONS_BINDING in APPLICATION_BINDINGS
    assert "resync_sessions" in TERMINAL_GATED_ACTIONS
    assert {binding.key for binding in APPLICATION_BINDINGS}.isdisjoint(
        {"ctrl+n", "ctrl+shift+s", "alt+m", "ctrl+d", "ctrl+q"}
    )
    assert TERMINAL_GATED_ACTIONS == {
        "command_palette",
        "focus_agents",
        "focus_shells",
        "resync_sessions",
    }
    assert {binding.key for binding in APPLICATION_BINDINGS}.isdisjoint(
        {str(number) for number in range(1, 10)}
    )


def test_sidebar_declares_no_local_navigation_bindings() -> None:
    assert "BINDINGS" not in SessionSidebar.__dict__


def test_textual_default_quit_binding_is_disabled() -> None:
    app = AgentHubApp()

    assert app.check_action("quit", ()) is False
