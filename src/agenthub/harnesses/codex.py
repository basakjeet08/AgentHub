"""Codex harness definition."""

from .model import AgentHarness

CODEX = AgentHarness(
    id="codex",
    display_name="Codex",
    command=("codex",),
    scroll=None,
    icon="🌀",
)
