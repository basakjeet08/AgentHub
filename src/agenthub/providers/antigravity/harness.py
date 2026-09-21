"""Google Antigravity CLI harness definition."""

from agenthub.harnesses import AgentHarness

ANTIGRAVITY = AgentHarness(
    id="antigravity",
    display_name="Antigravity",
    command=("agy",),
    scroll=None,
    icon="🛸",
)
