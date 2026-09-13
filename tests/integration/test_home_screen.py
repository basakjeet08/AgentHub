"""Integration tests for AgentHub's empty startup shell and Home UI."""

from textual.widgets import Button, OptionList, Static

from agenthub.app import AgentHubApp
from agenthub.terminal import AgentTerminal
from agenthub.ui import AgentHubStatusBar, HomeScreen, SessionSidebar
from agenthub.ui.bindings import HOME_SHORTCUT_BINDINGS


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
        assert not sidebar.query(OptionList).nodes
        assert sidebar.query_one("#sidebar-brand", Static).content == "AGENTHUB"

        status = app.query_one(AgentHubStatusBar)
        assert status.query_one("#status-label", Static).content == "Ready"
        assert status.query_one("#session-count", Static).content == "Sessions 0"
        assert status.query_one("#agent-count", Static).content == "Agents 0"

        shortcut_labels = [str(label.content) for label in home.query("#shortcut-grid Label")]
        expected_labels = [
            value
            for binding in HOME_SHORTCUT_BINDINGS
            for value in (binding.key_display or binding.key, binding.description)
        ]
        assert shortcut_labels == expected_labels


async def test_home_navigation_and_stub_actions_create_no_session() -> None:
    app = AgentHubApp()

    async with app.run_test(size=(100, 36)) as pilot:
        await pilot.pause()

        await pilot.press("ctrl+left")
        assert app.query_one("#sidebar-new-session", Button).has_focus

        await pilot.press("ctrl+right")
        assert app.query_one(HomeScreen).has_focus

        await pilot.press("ctrl+n")
        await pilot.click("#sidebar-new-session")
        assert app.session_manager.sessions == ()


async def test_new_session_button_stays_inside_percentage_sidebar() -> None:
    app = AgentHubApp()

    async with app.run_test(size=(60, 20)) as pilot:
        await pilot.pause()

        sidebar = app.query_one(SessionSidebar).region
        button = app.query_one("#sidebar-new-session", Button).region

        assert button.x >= sidebar.x
        assert button.x + button.width <= sidebar.x + sidebar.width
