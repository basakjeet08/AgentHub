"""Fish shell definition for AgentHub's shell sessions."""

from .model import AgentHarness

FISH = AgentHarness(
    id="fish",
    display_name="Fish",
    command=("fish",),
    scroll=None,
    icon="🐟",
)
