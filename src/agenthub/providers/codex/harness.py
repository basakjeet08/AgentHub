"""Codex harness definition."""

from agenthub.harnesses import AgentHarness

CODEX = AgentHarness(
    id="codex",
    display_name="Codex",
    command=("codex",),
    scroll=None,
    icon="🌀",
)
