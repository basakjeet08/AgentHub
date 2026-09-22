"""Devin CLI harness definition."""

from agenthub.harnesses import AgentHarness

DEVIN = AgentHarness(
    id="devin",
    display_name="Devin",
    command=("devin",),
    scroll=None,
    icon="🤖",
)
