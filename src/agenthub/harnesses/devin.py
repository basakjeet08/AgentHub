"""Devin CLI harness definition."""

from .model import AgentHarness

DEVIN = AgentHarness(
    id="devin",
    display_name="Devin",
    command=("devin",),
    scroll=None,
)
