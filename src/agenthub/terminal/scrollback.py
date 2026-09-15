"""Styled scrollback storage for embedded primary-screen terminals."""

from collections import deque
from collections.abc import Callable, Sequence

from bittty.video import Cell, Video
from bittty.width import WidthPolicy


class ScrollbackVideo(Video):
    """Bitty primary video page that retains rows lost to full-screen scrolling."""

    def __init__(
        self,
        width: int,
        height: int,
        width_policy: WidthPolicy,
        *,
        history_limit: int,
        on_history_added: Callable[[int], None],
    ) -> None:
        super().__init__(width, height, width_policy)
        self._history: deque[list[Cell]] = deque(maxlen=history_limit)
        self._on_history_added = on_history_added

    @property
    def history_line_count(self) -> int:
        """Return the number of retained rows."""

        return len(self._history)

    def history_row(self, index: int) -> Sequence[Cell]:
        """Return one retained styled row by oldest-first index."""

        return self._history[index]

    def _retain_rows(self, rows: Sequence[Sequence[Cell]]) -> None:
        """Copy rows into bounded history before Bitty discards them."""

        if not rows:
            return
        self._history.extend(list(row) for row in rows)
        self._on_history_added(len(rows))

    def scroll_up(self, count: int) -> None:
        """Retain rows removed by a full-page upward scroll."""

        retained_count = min(max(count, 0), len(self.grid))
        self._retain_rows(self.grid[:retained_count])
        super().scroll_up(count)

    def scroll_region_up(self, top: int, bottom: int, count: int) -> None:
        """Retain rows leaving a top-anchored primary-screen scroll region."""

        if top == 0 and count > 0:
            retained_count = min(count, bottom + 1, self.height)
            self._retain_rows(self.grid[:retained_count])
        super().scroll_region_up(top, bottom, count)

    def scroll_rectangle_up(
        self,
        top: int,
        bottom: int,
        count: int,
        *,
        left: int = 0,
        right: int | None = None,
        style_or_ansi: object = None,
    ) -> None:
        """Retain styled rows leaving a top-anchored full-width scroll region."""

        delegates_to_region = left == 0 and right is None and style_or_ansi is None
        effective_right = self.width - 1 if right is None else right
        if (
            not delegates_to_region
            and top == 0
            and left == 0
            and effective_right == self.width - 1
            and count > 0
        ):
            retained_count = min(count, bottom + 1, self.height)
            self._retain_rows(self.grid[:retained_count])
        super().scroll_rectangle_up(
            top,
            bottom,
            count,
            left=left,
            right=right,
            style_or_ansi=style_or_ansi,
        )
