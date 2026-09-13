"""Fish shell definition for AgentHub's fixed shell slots."""

from .model import AgentHarness

FISH = AgentHarness(
    id="fish",
    display_name="Fish",
    command=("fish",),
    scroll=None,
)
