"""Terminal widget adapter: textual-tty with app-specific input behavior."""

from dataclasses import dataclass

from textual import events
from textual_tty import Terminal as TtyTerminal


@dataclass(frozen=True)
class ScrollKeys:
    """
    Transcript-scroll policy: key+modifier per direction, ticks per wheel step.
    """

    down: tuple[str, int]
    up: tuple[str, int]
    steps: int = 3


class AgentTerminal(TtyTerminal):
    """textual-tty (bittty) terminal hosting the coding agent."""

    def __init__(
        self,
        command: str | list[str],
        *,
        scroll: ScrollKeys,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Build the terminal; scroll policy comes from the harness."""

        self._scroll = scroll
        super().__init__(command=command, name=name, id=id, classes=classes)

    async def on_key(self, event: events.Key) -> None:
        """Quit on Ctrl+Q; every other key falls through to the base widget."""

        if event.key == "ctrl+q":
            event.stop()
            self.app.exit()
            return

    def _wheel(self, event: events.MouseEvent, button: int, arrow: str) -> None:
        """Scroll the transcript when the child ignores the wheel; defer otherwise."""

        # When the child tracks the mouse it owns the wheel — defer to base.
        # Otherwise send the harness's transcript-scroll keys. Plain method
        # override (not a message handler), so super() here is a single call.
        if self.mouse_mode != "off":
            super()._wheel(event, button, arrow)
            return

        key, modifier = self._scroll.down if arrow == "down" else self._scroll.up

        for _ in range(self._scroll.steps):
            self.board.display.input_key(key, modifier)

        event.stop()
