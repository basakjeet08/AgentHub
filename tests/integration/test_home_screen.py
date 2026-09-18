"""Integration tests for AgentHub's empty startup shell and Home UI."""

from textual.color import Color
from textual.widgets import Button, OptionList, Static

from agenthub.app import AgentHubApp
from agenthub.terminal import AgentTerminal
from agenthub.ui import AgentHubStatusBar, HomeScreen, SessionSidebar, SidebarTab
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
        assert sidebar.selected_tab is SidebarTab.LOADED
        assert [
            str(sidebar.query_one(f"#sidebar-tab-{tab.value}", Static).content)
            for tab in SidebarTab
        ] == ["LOADED 0", "UNLOADED 0", "SHELLS 0"]
        assert len(sidebar.query(OptionList).nodes) == 1
        assert not sidebar.query_one(OptionList).options
        brand = sidebar.query_one("#sidebar-brand", Static)
        assert brand.styles.border_bottom == ("solid", Color.parse("#BB9AF7"))
        assert sidebar.query_one(OptionList).styles.overflow_y == "auto"

        status = app.query_one(AgentHubStatusBar)
        assert [child.id for child in status.children] == [
            "session-metrics",
            "lock-status",
        ]
        assert status.query_one("#mode-indicator", Static).content == UNLOCKED_ICON
        assert status.query_one("#mode-label", Static).content == "Unlocked"
        assert status.query_one("#mode-action", Static).content == "Ctrl+G Lock"
        assert status.query_one("#session-count", Static).content == "Sessions 0"
        assert status.query_one("#running-count", Static).content == "Running 0"
        assert (
            status.query_one("#running-count", Static).region.x
            < status.query_one("#mode-indicator", Static).region.x
        )

        shortcut_labels = [str(label.content) for label in home.query("#shortcut-grid Label")]
        expected_labels = [value for shortcut in HOME_SHORTCUTS for value in shortcut]
        assert shortcut_labels == expected_labels
        assert all(key != "Ctrl+0" for key, _description in HOME_SHORTCUTS)
        assert ("Ctrl+S", "Focus sidebar") in HOME_SHORTCUTS
        assert ("← / →", "Change sidebar tab") in HOME_SHORTCUTS
        assert ("↑ / ↓, Enter", "Navigate / open session") in HOME_SHORTCUTS
        assert all(
            key not in {"Ctrl+N", "Ctrl+Shift+S", "Alt+M", "Ctrl+D", "Ctrl+Q"}
            for key, _description in HOME_SHORTCUTS
        )
        assert ("Ctrl+P", "Command palette") in HOME_SHORTCUTS
        mode_note = home.query_one("#shortcut-mode-note", Static)
        quit_note = home.query_one("#shortcut-quit-note", Static)
        assert quit_note.content == (
            "Note: To quit AgentHub, press Ctrl+P and select Quit AgentHub."
        )
        assert quit_note.region.y == mode_note.region.bottom + 1


async def test_home_navigation_moves_focus_without_creating_a_session() -> None:
    app = AgentHubApp()

    async with app.run_test(size=(100, 36)) as pilot:
        await pilot.pause()

        await pilot.press("ctrl+a")
        assert not app.query_one(SessionSidebar).has_focus

        await pilot.press("ctrl+s")
        assert app.query_one(SessionSidebar).has_focus
        assert app.session_manager.sessions == ()
