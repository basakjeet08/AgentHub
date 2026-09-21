"""Integration tests for selecting text inside the terminal viewport."""

from textual.app import App, ComposeResult
from textual.geometry import Offset
from textual.selection import SELECT_ALL, Selection

from agenthub.harnesses import AgentHarness
from agenthub.terminal import AgentTerminal


class TerminalSelectionApp(App[None]):
    """A fixed-size terminal host for mouse-selection tests."""

    CSS = "AgentTerminal { width: 30; height: 5; }"

    def __init__(self, harness: AgentHarness) -> None:
        super().__init__()
        self.terminal = AgentTerminal(harness)

    def compose(self) -> ComposeResult:
        yield self.terminal


async def _populate_terminal(app: TerminalSelectionApp, pilot) -> AgentTerminal:
    terminal = app.terminal
    terminal.feed("alpha beta gamma\r\nsecond line")
    await pilot.pause()
    return terminal


async def test_drag_selects_only_requested_terminal_characters(
    sleeping_harness: AgentHarness,
) -> None:
    app = TerminalSelectionApp(sleeping_harness)

    async with app.run_test(size=(40, 10)) as pilot:
        terminal = await _populate_terminal(app, pilot)

        assert app.screen.get_widget_and_offset_at(6, 0) == (
            terminal,
            Offset(6, 0),
        )

        await pilot.mouse_down(terminal, offset=(6, 0))
        await pilot.hover(terminal, offset=(9, 0))
        await pilot.mouse_up(terminal, offset=(9, 0))

        assert app.screen.selections[terminal] == Selection(
            Offset(6, 0),
            Offset(10, 0),
        )
        assert app.screen.get_selected_text() == "beta"


async def test_copy_shortcut_uses_selected_terminal_text(
    sleeping_harness: AgentHarness,
) -> None:
    app = TerminalSelectionApp(sleeping_harness)

    async with app.run_test(size=(40, 10)) as pilot:
        terminal = await _populate_terminal(app, pilot)
        await pilot.mouse_down(terminal, offset=(6, 0))
        await pilot.hover(terminal, offset=(9, 0))
        await pilot.mouse_up(terminal, offset=(9, 0))

        await pilot.press("ctrl+shift+c")

        assert app.clipboard == "beta"


async def test_reverse_drag_preserves_terminal_selection_range(
    sleeping_harness: AgentHarness,
) -> None:
    app = TerminalSelectionApp(sleeping_harness)

    async with app.run_test(size=(40, 10)) as pilot:
        terminal = await _populate_terminal(app, pilot)

        await pilot.mouse_down(terminal, offset=(9, 0))
        await pilot.hover(terminal, offset=(6, 0))
        await pilot.mouse_up(terminal, offset=(6, 0))

        assert app.screen.get_selected_text() == "beta"


async def test_drag_selects_across_terminal_lines(
    sleeping_harness: AgentHarness,
) -> None:
    app = TerminalSelectionApp(sleeping_harness)

    async with app.run_test(size=(40, 10)) as pilot:
        terminal = await _populate_terminal(app, pilot)

        await pilot.mouse_down(terminal, offset=(6, 0))
        await pilot.hover(terminal, offset=(5, 1))
        await pilot.mouse_up(terminal, offset=(5, 1))

        assert app.screen.get_selected_text() == "beta gamma\nsecond"


async def test_wide_terminal_characters_are_extracted_by_cell_offset(
    sleeping_harness: AgentHarness,
) -> None:
    app = TerminalSelectionApp(sleeping_harness)

    async with app.run_test(size=(40, 10)) as pilot:
        terminal = app.terminal
        terminal.feed("A你B")
        await pilot.pause()
        await pilot.mouse_down(terminal, offset=(1, 0))
        await pilot.hover(terminal, offset=(2, 0))
        await pilot.mouse_up(terminal, offset=(2, 0))

        assert app.screen.get_selected_text() == "你"
        component_style = app.screen.get_component_rich_style("screen--selection")
        selected = terminal.render_line(0).crop(1, 3)
        after = terminal.render_line(0).crop(3, 4)
        assert all(segment.style.bgcolor == component_style.bgcolor for segment in selected)
        assert all(segment.style.bgcolor != component_style.bgcolor for segment in after)


async def test_multiline_wide_character_selection_uses_terminal_cells(
    sleeping_harness: AgentHarness,
) -> None:
    app = TerminalSelectionApp(sleeping_harness)

    async with app.run_test(size=(40, 10)) as pilot:
        terminal = app.terminal
        terminal.feed("A你B\r\nC🙂D")
        await pilot.pause()
        await pilot.mouse_down(terminal, offset=(1, 0))
        await pilot.hover(terminal, offset=(2, 1))
        await pilot.mouse_up(terminal, offset=(2, 1))

        assert app.screen.get_selected_text() == "你B\nC🙂"


async def test_double_click_after_wide_character_selects_clicked_word(
    sleeping_harness: AgentHarness,
) -> None:
    app = TerminalSelectionApp(sleeping_harness)

    async with app.run_test(size=(40, 10)) as pilot:
        terminal = app.terminal
        terminal.feed("你 B")
        await pilot.pause()
        await pilot.double_click(terminal, offset=(3, 0))

        assert app.screen.get_selected_text() == "B"


async def test_double_click_selects_word_instead_of_entire_terminal(
    sleeping_harness: AgentHarness,
) -> None:
    app = TerminalSelectionApp(sleeping_harness)

    async with app.run_test(size=(40, 10)) as pilot:
        terminal = await _populate_terminal(app, pilot)

        await pilot.double_click(terminal, offset=(7, 0))

        assert app.screen.selections[terminal] != SELECT_ALL
        assert app.screen.get_selected_text() == "beta"


async def test_selection_highlight_preserves_terminal_foreground_colors(
    sleeping_harness: AgentHarness,
) -> None:
    app = TerminalSelectionApp(sleeping_harness)
    app.theme = "tokyo-night"

    async with app.run_test(size=(40, 10)) as pilot:
        terminal = app.terminal
        terminal.feed("\x1b[31mvisible")
        await pilot.pause()
        original_style = next(iter(terminal.render_line(0).crop(0, 1))).style

        app.screen.selections = {
            terminal: Selection(Offset(0, 0), Offset(7, 0))
        }
        selected_style = next(iter(terminal.render_line(0).crop(0, 1))).style
        component_style = app.screen.get_component_rich_style("screen--selection")

        assert original_style is not None
        assert selected_style is not None
        assert selected_style.color == original_style.color
        assert selected_style.bgcolor == component_style.bgcolor
        assert selected_style.color != selected_style.bgcolor


async def test_terminal_selection_is_disabled_while_child_tracks_mouse(
    sleeping_harness: AgentHarness,
) -> None:
    app = TerminalSelectionApp(sleeping_harness)

    async with app.run_test(size=(40, 10)) as pilot:
        terminal = await _populate_terminal(app, pilot)
        terminal.mouse_mode = "normal"

        await pilot.mouse_down(terminal, offset=(6, 0))
        await pilot.hover(terminal, offset=(9, 0))
        await pilot.mouse_up(terminal, offset=(9, 0))

        assert terminal.mouse_mode != "off"
        assert terminal not in app.screen.selections


async def test_selection_copies_rows_visible_in_terminal_scrollback(
    sleeping_harness: AgentHarness,
) -> None:
    scrollback_harness = AgentHarness(
        id="test-scrollback",
        display_name="Test Scrollback",
        icon="🧪",
        command=sleeping_harness.command,
        scroll=None,
    )
    app = TerminalSelectionApp(scrollback_harness)

    async with app.run_test(size=(40, 10)) as pilot:
        terminal = app.terminal
        terminal.feed("one\r\ntwo\r\nthree\r\nfour\r\nfive\r\nsix")
        await pilot.pause()
        terminal._scroll_normal_history("up", 2)

        assert terminal._visible_line_text(0).rstrip() == "one"
        await pilot.mouse_down(terminal, offset=(0, 0))
        await pilot.hover(terminal, offset=(2, 0))
        await pilot.mouse_up(terminal, offset=(2, 0))
        await pilot.press("ctrl+shift+c")

        assert app.clipboard == "one"


async def test_wide_character_selection_uses_cells_in_scrollback(
    sleeping_harness: AgentHarness,
) -> None:
    scrollback_harness = AgentHarness(
        id="test-wide-scrollback",
        display_name="Test Wide Scrollback",
        icon="🧪",
        command=sleeping_harness.command,
        scroll=None,
    )
    app = TerminalSelectionApp(scrollback_harness)

    async with app.run_test(size=(40, 10)) as pilot:
        terminal = app.terminal
        terminal.feed("A你B\r\ntwo\r\nthree\r\nfour\r\nfive\r\nsix")
        await pilot.pause()
        terminal._scroll_normal_history("up", 2)
        await pilot.mouse_down(terminal, offset=(1, 0))
        await pilot.hover(terminal, offset=(2, 0))
        await pilot.mouse_up(terminal, offset=(2, 0))

        assert app.screen.get_selected_text() == "你"
