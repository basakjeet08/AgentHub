"""Tests for semantic harness configuration."""

from dataclasses import FrozenInstanceError

import pytest

from agenthub.harnesses import (
    ANTIGRAVITY,
    CODEX,
    DEFAULT_HARNESS,
    DEVIN,
    FISH,
    HARNESSES,
    OPENCODE,
    AgentHarness,
)


def test_opencode_uses_stable_registry_identity() -> None:
    assert DEFAULT_HARNESS == "opencode"
    assert HARNESSES[DEFAULT_HARNESS] is OPENCODE
    assert OPENCODE.display_name == "OpenCode"
    assert OPENCODE.command == ("opencode",)


@pytest.mark.parametrize(
    ("harness", "harness_id", "display_name", "command"),
    [
        (ANTIGRAVITY, "antigravity", "Antigravity", ("agy",)),
        (CODEX, "codex", "Codex", ("codex",)),
        (DEVIN, "devin", "Devin", ("devin",)),
    ],
)
def test_native_scrolling_harnesses_use_stable_registry_identity(
    harness: AgentHarness,
    harness_id: str,
    display_name: str,
    command: tuple[str, ...],
) -> None:
    assert harness.id == harness_id
    assert harness.display_name == display_name
    assert harness.command == command
    assert harness.scroll is None
    assert HARNESSES[harness.id] is harness


def test_registry_contains_only_supported_coding_agents() -> None:
    assert set(HARNESSES) == {
        ANTIGRAVITY.id,
        CODEX.id,
        DEVIN.id,
        OPENCODE.id,
    }


def test_fish_is_a_shell_runtime_without_agent_scroll_keys() -> None:
    assert FISH.id == "fish"
    assert FISH.display_name == "Fish"
    assert FISH.command == ("fish",)
    assert FISH.scroll is None
    assert FISH.id not in HARNESSES


def test_harness_configuration_is_deeply_immutable() -> None:
    with pytest.raises(FrozenInstanceError):
        OPENCODE.display_name = "Changed"  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        OPENCODE.scroll.steps = 1  # type: ignore[misc]
