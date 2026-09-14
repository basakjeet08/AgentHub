"""Integration tests for AgentHub's empty startup shell and Home UI."""

from textual.color import Color
from textual.widgets import Button, OptionList, Static

from agenthub.app import AgentHubApp
from agenthub.terminal import AgentTerminal
from agenthub.ui import AgentHubStatusBar, HomeScreen, SessionSidebar
from agenthub.ui.bindings import HOME_SHORTCUTS
from agenthub.ui.panels.status_bar import UNLOCKED_ICON


async def test_empty_startup_shows_home_sidebar_and_real_status() -> None:
    app = AgentHubApp()

    async with app.run_test(size=(100, 36)) as pilot:
        await pilot.pause()

        assert app.session_manager.sessions == ()
        assert not app.query(AgentTerminal).nodes
        home = app.query_one(HomeScreen)
        assert home.display
        assert home.has_focus
        assert not home.query(Button).nodes

        sidebar = app.query_one(SessionSidebar)
        assert sidebar.query_one("#sidebar-brand", Static).content == ">_  AGENTHUB"
        headings = [str(heading.content) for heading in sidebar.query(".sidebar-section-title")]
        assert headings == ["AGENTS", "SHELLS"]
        assert sidebar.query_one("#agent-section-shortcut", Static).content == "Ctrl+A"
        assert sidebar.query_one("#shell-section-shortcut", Static).content == "Ctrl+S"
        assert len(sidebar.query(OptionList).nodes) == 2
        assert all(not option_list.options for option_list in sidebar.query(OptionList))
        brand = sidebar.query_one("#sidebar-brand", Static)
        shell_section = sidebar.query_one("#shell-section")
        assert brand.styles.border_bottom == ("solid", Color.parse("#BB9AF7"))
        assert shell_section.styles.border_bottom[0] == ""
        assert shell_section.region.bottom == sidebar.content_region.bottom
        assert all(
            option_list.styles.overflow_y == "auto" for option_list in sidebar.query(OptionList)
        )

        status = app.query_one(AgentHubStatusBar)
        assert [child.id for child in status.children] == [
            "session-metrics",
            "lock-status",
        ]
        assert status.query_one("#mode-indicator", Static).content == UNLOCKED_ICON
        assert status.query_one("#mode-label", Static).content == "Unlocked"
        assert status.query_one("#mode-action", Static).content == "Ctrl+G Lock"
        assert status.query_one("#session-count", Static).content == "Sessions 0"
        assert status.query_one("#agent-count", Static).content == "Agents 0"
        assert (
            status.query_one("#agent-count", Static).region.x
            < status.query_one("#mode-indicator", Static).region.x
        )

        shortcut_labels = [str(label.content) for label in home.query("#shortcut-grid Label")]
        expected_labels = [value for shortcut in HOME_SHORTCUTS for value in shortcut]
        assert shortcut_labels == expected_labels
        assert all(key != "Ctrl+0" for key, _description in HOME_SHORTCUTS)
        assert ("Ctrl+A, then 1…9", "Switch agent session") in HOME_SHORTCUTS
        assert ("Ctrl+S, then 1…9", "Open / switch shell") in HOME_SHORTCUTS
        assert ("Ctrl+P", "Command palette") in HOME_SHORTCUTS


async def test_home_navigation_moves_focus_without_creating_a_session() -> None:
    app = AgentHubApp()

    async with app.run_test(size=(100, 36)) as pilot:
        await pilot.pause()

        await pilot.press("ctrl+a")
        assert app.query_one(SessionSidebar).has_focus

        await pilot.press("ctrl+s")
        assert app.query_one(SessionSidebar).has_focus
        assert app.session_manager.sessions == ()
