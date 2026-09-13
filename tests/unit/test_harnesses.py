"""Tests for semantic harness configuration."""

from dataclasses import FrozenInstanceError

import pytest

from agenthub.harnesses import DEFAULT_HARNESS, FISH, HARNESSES, OPENCODE


def test_opencode_uses_stable_registry_identity() -> None:
    assert DEFAULT_HARNESS == "opencode"
    assert HARNESSES[DEFAULT_HARNESS] is OPENCODE
    assert OPENCODE.display_name == "OpenCode"
    assert OPENCODE.command == ("opencode",)


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
