"""Unit tests for application orchestration and ownership."""

from agenthub.app import AgentHubApp
from agenthub.ui.bindings import (
    APPLICATION_BINDINGS,
    COMMAND_PALETTE_BINDING,
    FOCUS_AGENTS_BINDING,
    FOCUS_SHELLS_BINDING,
    NEW_SESSION_BINDING,
    QUIT_BINDING,
    SHELL_SLOT_BINDINGS,
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


def test_application_bindings_are_priority_candidates_for_keyboard_ownership() -> None:
    assert list(APPLICATION_BINDINGS) == AgentHubApp.BINDINGS

    assert TOGGLE_HUB_LOCK_BINDING.key == "ctrl+g"
    assert TOGGLE_HUB_LOCK_BINDING.action == "toggle_hub_lock"
    assert TOGGLE_HUB_LOCK_BINDING.priority is True
    assert QUIT_BINDING.key == "ctrl+q"
    assert QUIT_BINDING.action == "quit"
    assert QUIT_BINDING.priority is True


def test_application_navigation_bindings_are_reserved() -> None:
    assert NEW_SESSION_BINDING.action == "new_session"
    assert FOCUS_AGENTS_BINDING.key == "ctrl+a"
    assert FOCUS_AGENTS_BINDING.action == "focus_agents"
    assert FOCUS_SHELLS_BINDING.key == "ctrl+s"
    assert FOCUS_SHELLS_BINDING.action == "focus_shells"
    assert all(
        binding.priority
        for binding in (
            NEW_SESSION_BINDING,
            FOCUS_AGENTS_BINDING,
            FOCUS_SHELLS_BINDING,
        )
    )
    assert COMMAND_PALETTE_BINDING.key == "ctrl+p"
    assert COMMAND_PALETTE_BINDING.action == "command_palette"
    assert COMMAND_PALETTE_BINDING.priority is True
    assert [binding.key for binding in SHELL_SLOT_BINDINGS] == [
        f"ctrl+{slot}" for slot in range(1, 10)
    ]
    assert [binding.description for binding in SHELL_SLOT_BINDINGS] == [
        f"Fish shell {slot}" for slot in range(1, 10)
    ]
    assert all(binding.priority for binding in SHELL_SLOT_BINDINGS)
