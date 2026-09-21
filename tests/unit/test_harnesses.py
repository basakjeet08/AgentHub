"""Tests for semantic harness configuration."""

from dataclasses import FrozenInstanceError

import pytest

from agenthub.harnesses import FISH, AgentHarness
from agenthub.providers import (
    ANTIGRAVITY,
    CODEX,
    DEFAULT_HARNESS,
    DEVIN,
    HARNESSES,
    OPENCODE,
)
from agenthub.providers.antigravity import ANTIGRAVITY as ANTIGRAVITY_PACKAGE
from agenthub.providers.codex import CODEX as CODEX_PACKAGE
from agenthub.providers.devin import DEVIN as DEVIN_PACKAGE
from agenthub.providers.opencode import OPENCODE as OPENCODE_PACKAGE


def test_opencode_uses_stable_registry_identity() -> None:
    assert DEFAULT_HARNESS == "opencode"
    assert HARNESSES[DEFAULT_HARNESS] is OPENCODE
    assert OPENCODE.display_name == "OpenCode"
    assert OPENCODE.command == ("opencode",)
    assert OPENCODE.icon == "💻"
    assert OPENCODE.scroll is not None
    assert OPENCODE.scroll.down.key == "e"
    assert OPENCODE.scroll.down.ctrl is True
    assert OPENCODE.scroll.down.alt is True
    assert OPENCODE.scroll.up.key == "y"
    assert OPENCODE.scroll.up.ctrl is True
    assert OPENCODE.scroll.up.alt is True
    assert OPENCODE.scroll.steps == 3


@pytest.mark.parametrize(
    ("harness", "harness_id", "display_name", "command", "icon"),
    [
        (ANTIGRAVITY, "antigravity", "Antigravity", ("agy",), "🛸"),
        (CODEX, "codex", "Codex", ("codex",), "🌀"),
        (DEVIN, "devin", "Devin", ("devin",), "🤖"),
    ],
)
def test_native_scrolling_harnesses_use_stable_registry_identity(
    harness: AgentHarness,
    harness_id: str,
    display_name: str,
    command: tuple[str, ...],
    icon: str,
) -> None:
    assert harness.id == harness_id
    assert harness.display_name == display_name
    assert harness.command == command
    assert harness.scroll is None
    assert harness.icon == icon
    assert HARNESSES[harness.id] is harness


def test_registry_contains_only_supported_coding_agents() -> None:
    assert set(HARNESSES) == {
        ANTIGRAVITY.id,
        CODEX.id,
        DEVIN.id,
        OPENCODE.id,
    }


def test_registry_is_ordered_by_display_name() -> None:
    display_names = [harness.display_name for harness in HARNESSES.values()]

    assert display_names == sorted(display_names, key=str.casefold)


@pytest.mark.parametrize(
    ("package_harness", "registry_harness"),
    [
        (ANTIGRAVITY_PACKAGE, ANTIGRAVITY),
        (CODEX_PACKAGE, CODEX),
        (DEVIN_PACKAGE, DEVIN),
        (OPENCODE_PACKAGE, OPENCODE),
    ],
)
def test_provider_packages_export_their_registered_harness(
    package_harness: AgentHarness,
    registry_harness: AgentHarness,
) -> None:
    assert package_harness is registry_harness


def test_fish_is_a_shell_runtime_without_agent_scroll_keys() -> None:
    assert FISH.id == "fish"
    assert FISH.display_name == "Fish"
    assert FISH.command == ("fish",)
    assert FISH.scroll is None
    assert FISH.icon == "🐟"
    assert FISH.id not in HARNESSES


def test_harness_configuration_is_deeply_immutable() -> None:
    with pytest.raises(FrozenInstanceError):
        OPENCODE.display_name = "Changed"  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        OPENCODE.icon = "Changed"  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        OPENCODE.scroll.steps = 1  # type: ignore[misc]
