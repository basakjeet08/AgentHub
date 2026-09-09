"""Agent harness abstraction: one swappable backend per agent CLI."""

from abc import ABC, abstractmethod

from bittty import constants as _bittty_constants
from textual.widget import Widget

from .widget import AgentTerminal, ScrollKeys


class AgentHarness(ABC):
    """What AgentHub needs from an agent backend: a command and its widget."""

    name: str
    command: str | list[str]
    scroll: ScrollKeys

    @abstractmethod
    def create_widget(self, **kwargs) -> Widget:
        """Build the terminal widget hosting this harness's command."""
        ...


class OpencodeHarness(AgentHarness):
    """opencode agent CLI (default harness)."""

    name = "opencode"
    command = "opencode"
    scroll = ScrollKeys(
        down=("e", _bittty_constants.KEY_MOD_ALT_CTRL),
        up=("y", _bittty_constants.KEY_MOD_ALT_CTRL),
    )

    def create_widget(self, **kwargs) -> AgentTerminal:
        """Build an AgentTerminal with opencode's command and scroll keys."""

        return AgentTerminal(
            command=self.command,
            scroll=self.scroll,
            **kwargs,
        )


# List of built in harnesses.
HARNESSES: dict[str, AgentHarness] = {
    OpencodeHarness.name: OpencodeHarness(),
}

# Default harness.
DEFAULT_HARNESS = OpencodeHarness.name
