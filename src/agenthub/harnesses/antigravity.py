"""Google Antigravity CLI harness definition."""

from .model import AgentHarness

ANTIGRAVITY = AgentHarness(
    id="antigravity",
    display_name="Antigravity",
    command=("agy",),
    scroll=None,
)
