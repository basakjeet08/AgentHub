"""Tests for semantic harness configuration."""

from dataclasses import FrozenInstanceError

import pytest

from agenthub.harnesses import DEFAULT_HARNESS, HARNESSES, OPENCODE


def test_opencode_uses_stable_registry_identity() -> None:
    assert DEFAULT_HARNESS == "opencode"
    assert HARNESSES[DEFAULT_HARNESS] is OPENCODE
    assert OPENCODE.display_name == "OpenCode"
    assert OPENCODE.command == ("opencode",)


def test_harness_configuration_is_deeply_immutable() -> None:
    with pytest.raises(FrozenInstanceError):
        OPENCODE.display_name = "Changed"  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        OPENCODE.scroll.steps = 1  # type: ignore[misc]
