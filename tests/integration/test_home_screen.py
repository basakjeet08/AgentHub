"""Integration tests for AgentHub's empty startup shell and Home UI."""

from textual.color import Color
from textual.widgets import (
    Button,
    OptionList,
    Static,
    Tab,
    TabbedContent,
    TabPane,
    Tabs,
)

from agenthub.app import AgentHubApp
from agenthub.terminal import AgentTerminal
from agenthub.ui import AgentHubStatusBar, HomeScreen, SessionSidebar, SidebarTab
from agenthub.ui.bindings import APPLICATION_BINDINGS
from agenthub.ui.panels.status_bar import UNLOCKED_ICON

_HOME_CARD_IDS = [
    "home-card-getting-started",
    "home-card-navigation-basics",
    "home-card-session-management",
    "home-card-controls-shortcuts",
]

_HOME_CARD_TITLES = [
    "GETTING STARTED",
    "NAVIGATION BASICS",
    "SESSION MANAGEMENT",
    "CONTROLS & SHORTCUTS",
]

_HOME_PANE_IDS = [
    "home-pane-getting-started",
    "home-pane-navigation-basics",
    "home-pane-session-management",
    "home-pane-controls-shortcuts",
]

_HOME_TAB_LABELS = ["Start Here", "Navigation", "Sessions", "Shortcuts"]


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
        assert not home.query("#home-empty-copy").nodes

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

        cards = list(home.query(".home-card"))
        panes = list(home.query(TabPane))
        tabs = home.query_one(Tabs)
        tabbed_content = home.query_one(TabbedContent)
        assert [card.id for card in cards] == _HOME_CARD_IDS
        assert [pane.id for pane in panes] == _HOME_PANE_IDS
        assert [str(tab.label) for tab in tabs.query(Tab)] == _HOME_TAB_LABELS
        assert not tabs.can_focus
        assert tabbed_content.active == _HOME_PANE_IDS[0]
        assert [pane.display for pane in panes] == [True, False, False, False]
        assert [
            str(card.query_one(".home-card-title", Static).content) for card in cards
        ] == _HOME_CARD_TITLES
        assert all(not card.can_focus for card in cards)
        assert all(not descendant.can_focus for card in cards for descendant in card.query("*"))

        home_copy = "\n".join(str(widget.content) for widget in home.query(Static))
        for expected in (
            "What is AgentHub?",
            "Loaded",
            "New Agent",
            "Command Palette",
            "Sidebar Navigation",
            "Resume an Existing Agent",
            "Link an Agent",
            "Refresh Sessions",
            "Delete an Agent",
            "Keyboard Control",
            "Global Shortcuts",
            "Ctrl+P → Quit AgentHub",
        ):
            assert expected in home_copy
        assert home.query_one("#home-quick-reference", Static).content == (
            "Ctrl+P Commands  •  Ctrl+S Sidebar  •  Ctrl+G Lock/Unlock  •  Ctrl+Shift+R Refresh"
        )

        assert AgentHubApp.BINDINGS == list(APPLICATION_BINDINGS)
        assert [(binding.key, binding.action) for binding in APPLICATION_BINDINGS] == [
            ("ctrl+g", "toggle_hub_lock"),
            ("ctrl+p", "command_palette"),
            ("ctrl+shift+r", "resync_sessions"),
            ("ctrl+s", "focus_sidebar"),
        ]
        assert "BINDINGS" not in HomeScreen.__dict__


async def test_home_navigation_moves_focus_without_creating_a_session() -> None:
    app = AgentHubApp()

    async with app.run_test(size=(100, 36)) as pilot:
        await pilot.pause()

        await pilot.press("ctrl+a")
        assert not app.query_one(SessionSidebar).has_focus

        tabs = app.query_one(HomeScreen).query_one(Tabs)
        await pilot.press("right")
        assert not tabs.has_focus
        assert app.query_one(TabbedContent).active == _HOME_PANE_IDS[0]

        await pilot.click("#--content-tab-home-pane-navigation-basics")
        assert app.query_one(TabbedContent).active == _HOME_PANE_IDS[1]
        assert not tabs.has_focus

        await pilot.press("ctrl+s")
        assert app.query_one(SessionSidebar).has_focus
        assert app.session_manager.sessions == ()


async def test_home_tabs_switch_visible_static_card_at_wide_sizes() -> None:
    app = AgentHubApp(native_session_adapters={})

    async with app.run_test(size=(150, 90)) as pilot:
        await pilot.pause()

        home = app.query_one(HomeScreen)
        cards = list(home.query(".home-card"))
        panes = list(home.query(TabPane))

        assert not home.has_class("narrow")
        assert panes[0].display
        assert cards[0].region.width > 0
        assert all(card.region.width == 0 for card in cards[1:])
        assert home.max_scroll_x == 0

        await pilot.click("#--content-tab-home-pane-controls-shortcuts")
        await pilot.pause()

        assert home.query_one(TabbedContent).active == _HOME_PANE_IDS[3]
        assert [pane.display for pane in panes] == [False, False, False, True]
        assert cards[3].region.width > 0
        assert cards[3].max_scroll_y == 0


async def test_home_session_tab_uses_page_scroll_at_narrow_sizes() -> None:
    app = AgentHubApp(native_session_adapters={})

    async with app.run_test(size=(90, 40)) as pilot:
        await pilot.pause()

        home = app.query_one(HomeScreen)
        cards = list(home.query(".home-card"))

        assert home.has_class("narrow")
        assert home.max_scroll_x == 0

        await pilot.click("#--content-tab-home-pane-session-management")
        await pilot.pause()

        assert home.query_one(TabbedContent).active == _HOME_PANE_IDS[2]
        assert cards[2].region.width > 0 and cards[2].region.height > 0
        assert cards[2].max_scroll_y == 0
        assert home.max_scroll_y > 0
        assert home.max_scroll_x == 0
