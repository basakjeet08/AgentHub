"""Integration tests for AgentHub's empty startup shell and Home UI."""

from textual.color import Color
from textual.widgets import Button, OptionList, Static

from agenthub.app import AgentHubApp
from agenthub.native_sessions import NativeSessionService
from agenthub.presentation import HomeScreen, SessionSidebar, SidebarTab
from agenthub.presentation.key_bindings import APPLICATION_BINDINGS
from agenthub.presentation.panels.sidebar import UNLOCKED_ICON
from agenthub.terminal import AgentTerminal

_GLOBAL_REFERENCE = [
    ("Ctrl+G", "Lock / unlock"),
    ("Ctrl+P", "Command palette"),
    ("Ctrl+S", "Focus sidebar"),
    ("Ctrl+Shift+R", "Refresh native sessions"),
]

_SIDEBAR_REFERENCE = [
    ("← / →", "Change sidebar tab"),
    ("↑ / ↓", "Navigate sessions"),
    ("Enter", "Open / resume"),
]


async def test_empty_startup_shows_static_home_and_sidebar() -> None:
    app = AgentHubApp()

    async with app.run_test(size=(100, 36)) as pilot:
        await pilot.pause()

        assert app.session_manager.sessions == ()
        assert not app.query(AgentTerminal).nodes
        home = app.query_one(HomeScreen)
        assert home.display
        assert home.has_focus
        assert not home.query(Button).nodes
        assert str(home.query_one("#home-title", Static).content) == "AgentHub"
        assert str(home.query_one("#home-tagline", Static).content) == ("Your agents live here.")
        assert "Ctrl+P" in str(home.query_one("#home-orientation", Static).content)
        readme_hint = home.query_one("#home-readme-hint", Static)
        assert readme_hint.content == ("See [$secondary]README.md[/] for the full usage guide.")
        assert readme_hint.render().plain == "See README.md for the full usage guide."

        shortcut_keys = [str(widget.content) for widget in home.query(".home-shortcut-key")]
        shortcut_descriptions = [
            str(widget.content) for widget in home.query(".home-shortcut-description")
        ]
        expected_reference = [*_GLOBAL_REFERENCE, *_SIDEBAR_REFERENCE]
        assert shortcut_keys == [key for key, _description in expected_reference]
        assert shortcut_descriptions == [description for _key, description in expected_reference]
        assert all(not descendant.can_focus for descendant in home.query("*"))

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

        assert sidebar.query_one("#sidebar-mode-indicator", Static).content == UNLOCKED_ICON
        assert sidebar.query_one("#sidebar-mode-label", Static).content == "Unlocked"
        assert sidebar.query_one("#sidebar-mode-action", Static).content == "Ctrl+G Lock"
        lock_status = sidebar.query_one("#sidebar-lock-status")
        assert lock_status.region.bottom == sidebar.content_region.bottom
        assert lock_status.content_region.height == 1

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

        await pilot.press("ctrl+s")
        assert app.query_one(SessionSidebar).has_focus
        assert app.session_manager.sessions == ()


async def test_home_quick_reference_has_no_horizontal_overflow_when_narrow() -> None:
    app = AgentHubApp(native_session_service=NativeSessionService({}))

    async with app.run_test(size=(70, 30)) as pilot:
        await pilot.pause()

        home = app.query_one(HomeScreen)
        reference = home.query_one("#home-quick-reference")

        assert home.max_scroll_x == 0
        assert reference.region.width > 0
        assert reference.region.right <= home.content_region.right
        assert reference.max_scroll_y == 0
