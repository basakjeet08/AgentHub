"""Integration coverage for the three-stage New Agent Session workflow."""

import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, patch

from textual.command import CommandPalette
from textual.pilot import Pilot
from textual.widgets import ContentSwitcher, Input, Label, OptionList, Static

from agenthub.app import AgentHubApp
from agenthub.harnesses import HARNESSES, AgentHarness
from agenthub.sessions import SessionKind
from agenthub.ui import HomeScreen, SessionSidebar
from agenthub.ui.modals import (
    HarnessSelectionModal,
    SessionNameModal,
    WorkingDirectoryModal,
)
from agenthub.ui.modals.working_directory import FolderTree


async def _open_name_modal(app: AgentHubApp, pilot: Pilot) -> SessionNameModal:
    """Select the currently highlighted harness without creating a runtime."""

    await pilot.press("ctrl+n")
    await pilot.press("enter")
    await pilot.pause()
    assert isinstance(app.screen, SessionNameModal)
    return app.screen


async def _open_working_directory_modal(
    app: AgentHubApp,
    pilot: Pilot,
    name: str = "Test Agent",
) -> WorkingDirectoryModal:
    """Advance through harness selection and naming without creating a runtime."""

    await _open_name_modal(app, pilot)
    app.screen.query_one("#session-name-input", Input).value = name
    await pilot.press("enter")
    await pilot.pause()
    assert isinstance(app.screen, WorkingDirectoryModal)
    return app.screen


async def _load_tree(tree: FolderTree) -> None:
    """Wait for a deterministic view of the tree's current root."""

    await tree.reload_node(tree.root)


async def _confirm_directory(
    app: AgentHubApp,
    pilot: Pilot,
    directory: Path,
) -> None:
    """Move the native cursor and confirm exactly once with Enter."""

    assert isinstance(app.screen, WorkingDirectoryModal)
    tree = app.screen.query_one(FolderTree)
    await _load_tree(tree)
    target = tree.root
    if target.data is None or target.data.path.resolve() != directory.resolve():
        target = next(
            node
            for node in tree.root.children
            if node.data is not None and node.data.path.resolve() == directory.resolve()
        )
    tree.move_cursor(target)
    await pilot.press("enter")
    await pilot.pause()


async def test_ctrl_n_opens_registry_derived_harness_modal_without_creating() -> None:
    app = AgentHubApp()

    async with app.run_test(size=(100, 36)) as pilot:
        await pilot.press("ctrl+n")
        await pilot.pause()

        assert isinstance(app.screen, HarnessSelectionModal)
        assert app.session_manager.sessions == ()
        harness_list = app.screen.query_one("#harness-selection-list", OptionList)
        assert harness_list.has_focus
        assert harness_list.highlighted == 0
        assert str(app.screen.query_one("#harness-selection-title", Label).content) == (
            "Select a harness"
        )
        cancel = app.screen.query_one("#harness-selection-cancel")
        assert str(cancel.query_one(".modal-shortcut-key", Static).content) == "Esc"
        assert (
            str(cancel.query_one(".modal-shortcut-description", Static).content)
            == "Cancel"
        )
        assert not app.screen.query("#harness-selection-prompt")
        assert tuple((option.id, str(option.prompt)) for option in harness_list.options) == tuple(
            (harness.id, harness.display_name)
            for harness in sorted(
                HARNESSES.values(),
                key=lambda harness: harness.display_name.casefold(),
            )
        )


async def test_escape_from_harness_modal_preserves_empty_home() -> None:
    app = AgentHubApp()

    async with app.run_test() as pilot:
        await pilot.press("ctrl+n")
        await pilot.press("escape")
        await pilot.pause()

        assert not isinstance(app.screen, HarnessSelectionModal)
        assert app.session_manager.sessions == ()
        assert app.query_one("#session-content", ContentSwitcher).current == "home-screen"
        assert app.query_one(HomeScreen).has_focus
        assert app.is_running

        await pilot.press("ctrl+p")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert isinstance(app.screen, CommandPalette)


async def test_harness_confirmation_opens_focused_name_modal_without_creating(
    sleeping_harness: AgentHarness,
) -> None:
    app = AgentHubApp(agent_harnesses={sleeping_harness.id: sleeping_harness})

    async with app.run_test() as pilot:
        name_modal = await _open_name_modal(app, pilot)

        assert app.session_manager.sessions == ()
        assert name_modal.query_one("#session-name-input", Input).has_focus
        assert name_modal.query_one("#session-name-input", Input).value == ""
        harness_context = name_modal.query_one("#session-name-harness", Static)
        assert str(harness_context.content) == f"Harness: {sleeping_harness.display_name}"
        cancel = name_modal.query_one("#session-name-cancel")
        assert str(cancel.query_one(".modal-shortcut-key", Static).content) == "Esc"
        assert (
            str(cancel.query_one(".modal-shortcut-description", Static).content)
            == "Cancel"
        )


async def test_escape_from_name_modal_cancels_the_entire_workflow(
    sleeping_harness: AgentHarness,
) -> None:
    app = AgentHubApp(agent_harnesses={sleeping_harness.id: sleeping_harness})

    async with app.run_test() as pilot:
        await _open_name_modal(app, pilot)
        await pilot.press("escape")
        await pilot.pause()

        assert not isinstance(
            app.screen,
            (HarnessSelectionModal, SessionNameModal, WorkingDirectoryModal),
        )
        assert app.session_manager.sessions == ()
        assert not app.query("AgentTerminal")
        assert app.query_one("#session-content", ContentSwitcher).current == "home-screen"
        assert app.query_one(HomeScreen).has_focus
        assert not app.hub_locked
        assert app.is_running


async def test_empty_names_remain_in_modal_with_validation(
    sleeping_harness: AgentHarness,
) -> None:
    app = AgentHubApp(agent_harnesses={sleeping_harness.id: sleeping_harness})

    async with app.run_test() as pilot:
        name_modal = await _open_name_modal(app, pilot)
        name_input = name_modal.query_one("#session-name-input", Input)

        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, SessionNameModal)
        assert name_input.has_focus
        assert str(name_modal.query_one("#session-name-error", Static).content)
        assert app.session_manager.sessions == ()

        name_input.value = "   "
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, SessionNameModal)
        assert name_input.has_focus
        assert app.session_manager.sessions == ()


async def test_ctrl_v_pastes_external_clipboard_text_into_name(
    sleeping_harness: AgentHarness,
) -> None:
    app = AgentHubApp(agent_harnesses={sleeping_harness.id: sleeping_harness})

    async with app.run_test() as pilot:
        name_modal = await _open_name_modal(app, pilot)
        name_input = name_modal.query_one("#session-name-input", Input)

        with patch(
            "agenthub.ui.modals.session_name._read_system_clipboard",
            return_value="Clipboard Session",
        ):
            await pilot.press("ctrl+v")
            await pilot.pause()

        assert name_input.value == "Clipboard Session"
        assert name_input.has_focus
        assert app.session_manager.sessions == ()


async def test_non_text_clipboard_does_not_change_name_input(
    sleeping_harness: AgentHarness,
) -> None:
    app = AgentHubApp(agent_harnesses={sleeping_harness.id: sleeping_harness})

    async with app.run_test() as pilot:
        name_modal = await _open_name_modal(app, pilot)
        name_input = name_modal.query_one("#session-name-input", Input)
        name_input.value = "Keep this name"
        name_input.select_all()

        with patch(
            "agenthub.ui.modals.session_name._read_system_clipboard",
            return_value="",
        ):
            await pilot.press("ctrl+v")
            await pilot.pause()

        assert name_input.value == "Keep this name"
        assert name_input.has_focus


async def test_name_confirmation_opens_focused_directory_modal_without_creating(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        working_directory_root=tmp_path,
    )

    async with app.run_test() as pilot:
        modal = await _open_working_directory_modal(
            app,
            pilot,
            "  AgentHub Refactor  ",
        )

        assert app.session_manager.sessions == ()
        assert not app.query("AgentTerminal")
        assert modal.query_one(FolderTree).path == tmp_path.resolve()
        assert modal.query_one(FolderTree).has_focus
        cancel = modal.query_one("#working-directory-cancel")
        assert str(cancel.query_one(".modal-shortcut-key", Static).content) == "Esc"
        assert (
            str(cancel.query_one(".modal-shortcut-description", Static).content)
            == "Cancel"
        )


async def test_directory_modal_uses_compact_height_and_header_spacing(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        working_directory_root=tmp_path,
    )

    async with app.run_test(size=(100, 36)) as pilot:
        modal = await _open_working_directory_modal(app, pilot)
        dialog = modal.query_one("#working-directory-dialog")
        header = modal.query_one("#working-directory-header")
        title = modal.query_one("#working-directory-title")
        tree = modal.query_one(FolderTree)

        assert dialog.region.height == 25
        assert header.region.height == 2
        assert tree.region.y == title.region.bottom + 1


async def test_ctrl_n_does_not_stack_a_second_workflow_over_directory_modal(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        working_directory_root=tmp_path,
    )

    async with app.run_test() as pilot:
        modal = await _open_working_directory_modal(app, pilot)
        await pilot.press("ctrl+n")
        await pilot.pause()

        assert app.screen is modal
        assert app.session_manager.sessions == ()


async def test_escape_from_directory_modal_preserves_empty_home(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        working_directory_root=tmp_path,
    )

    async with app.run_test() as pilot:
        await _open_working_directory_modal(app, pilot)
        await pilot.press("escape")
        await pilot.pause()

        assert app.session_manager.sessions == ()
        assert not app.query("AgentTerminal")
        assert app.query_one("#session-content", ContentSwitcher).current == "home-screen"
        assert app.query_one(HomeScreen).has_focus
        assert app.is_running


async def test_directory_modal_shows_folders_and_hides_files(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    project_a = tmp_path / "project-a"
    project_b = tmp_path / "project-b"
    project_a.mkdir()
    project_b.mkdir()
    (tmp_path / "README.md").touch()
    (tmp_path / "test.py").touch()
    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        working_directory_root=tmp_path,
    )

    async with app.run_test() as pilot:
        modal = await _open_working_directory_modal(app, pilot)
        tree = modal.query_one(FolderTree)
        await _load_tree(tree)

        visible_paths = {
            child.data.path.resolve()
            for child in tree.root.children
            if child.data is not None
        }
        assert visible_paths == {project_a.resolve(), project_b.resolve()}

        await pilot.press("escape")
        await pilot.pause()


async def test_ctrl_h_toggles_hidden_directories_without_creating_runtime(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    visible = tmp_path / "visible-project"
    hidden = tmp_path / ".hidden-project"
    nested = visible / "nested-project"
    hidden_nested = visible / ".hidden-nested-project"
    nested.mkdir(parents=True)
    hidden_nested.mkdir()
    hidden.mkdir()
    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        working_directory_root=tmp_path,
    )

    async with app.run_test() as pilot:
        modal = await _open_working_directory_modal(app, pilot)
        tree = modal.query_one(FolderTree)
        hidden_help = modal.query_one("#working-directory-hidden-help", Static)
        await _load_tree(tree)

        assert {
            child.data.path.resolve()
            for child in tree.root.children
            if child.data is not None
        } == {visible.resolve()}
        assert str(hidden_help.content) == "Show Hidden"
        visible_node = next(
            child
            for child in tree.root.children
            if child.data is not None and child.data.path.resolve() == visible.resolve()
        )
        tree.move_cursor(visible_node)
        await pilot.press("right")
        await tree._load_queue.join()
        assert visible_node.is_expanded
        assert {
            child.data.path.resolve()
            for child in visible_node.children
            if child.data is not None
        } == {nested.resolve()}

        await pilot.press("ctrl+h")
        await pilot.pause()

        assert tree.show_hidden
        assert {
            child.data.path.resolve()
            for child in tree.root.children
            if child.data is not None
        } == {visible.resolve(), hidden.resolve()}
        visible_node = next(
            child
            for child in tree.root.children
            if child.data is not None and child.data.path.resolve() == visible.resolve()
        )
        assert visible_node.is_expanded
        assert {
            child.data.path.resolve()
            for child in visible_node.children
            if child.data is not None
        } == {nested.resolve(), hidden_nested.resolve()}
        assert str(hidden_help.content) == "Hide Hidden"
        assert tree.has_focus
        assert app.session_manager.sessions == ()

        await pilot.press("ctrl+h")
        await pilot.pause()

        assert not tree.show_hidden
        assert {
            child.data.path.resolve()
            for child in tree.root.children
            if child.data is not None
        } == {visible.resolve()}
        visible_node = next(
            child
            for child in tree.root.children
            if child.data is not None and child.data.path.resolve() == visible.resolve()
        )
        assert visible_node.is_expanded
        assert {
            child.data.path.resolve()
            for child in visible_node.children
            if child.data is not None
        } == {nested.resolve()}
        assert str(hidden_help.content) == "Show Hidden"
        assert tree.has_focus
        assert app.session_manager.sessions == ()


async def test_typing_filters_current_directory_and_backspace_restores_entries(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    projects = tmp_path / "Projects"
    directories = tuple(
        projects / name
        for name in ("api", "docs", "portfolio", "prototype")
    )
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
    (projects / "project-notes.txt").touch()
    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        working_directory_root=tmp_path,
    )

    async with app.run_test() as pilot:
        modal = await _open_working_directory_modal(app, pilot)
        tree = modal.query_one(FolderTree)
        filter_value = modal.query_one("#working-directory-filter-value", Static)
        await _load_tree(tree)
        projects_node = next(
            child
            for child in tree.root.children
            if child.data is not None and child.data.path.resolve() == projects.resolve()
        )
        tree.move_cursor(projects_node)
        await pilot.press("right")
        await tree._load_queue.join()
        api_node = next(
            child
            for child in projects_node.children
            if child.data is not None and child.data.path.name == "api"
        )
        tree.move_cursor(api_node)
        await pilot.press("right")
        await tree._load_queue.join()
        assert api_node.is_expanded
        tree.move_cursor(projects_node)

        await pilot.press("P")
        await pilot.pause()

        projects_node = next(
            child
            for child in tree.root.children
            if child.data is not None and child.data.path.resolve() == projects.resolve()
        )
        assert tree.name_filter_directory == projects.resolve()
        assert tree.name_filter_query == "P"
        assert tuple(
            child.data.path.name
            for child in projects_node.children
            if child.data is not None
        ) == ("api", "portfolio", "prototype")
        assert tree.cursor_node is not None
        assert tree.cursor_node.data is not None
        assert tree.cursor_node.data.path.name == "api"

        await pilot.press("o")
        await pilot.pause()

        projects_node = next(
            child
            for child in tree.root.children
            if child.data is not None and child.data.path.resolve() == projects.resolve()
        )
        assert tree.name_filter_query == "Po"
        assert tuple(
            child.data.path.name
            for child in projects_node.children
            if child.data is not None
        ) == ("portfolio",)
        assert tree.name_filter_directory == projects.resolve()
        assert tree.cursor_node is not None
        assert tree.cursor_node.data is not None
        assert tree.cursor_node.data.path.name == "portfolio"
        assert str(filter_value.content) == f"{projects.resolve()}: Po"
        assert filter_value.has_class("active-filter")
        assert app.session_manager.sessions == ()

        await pilot.press("backspace")
        await pilot.pause()

        assert tree.name_filter_query == "P"
        assert tree.cursor_node is not None
        assert tree.cursor_node.data is not None
        assert tree.cursor_node.data.path.name == "api"

        await pilot.press("backspace")
        await pilot.pause()

        projects_node = next(
            child
            for child in tree.root.children
            if child.data is not None and child.data.path.resolve() == projects.resolve()
        )
        assert tree.name_filter_directory is None
        assert tree.name_filter_query == ""
        assert tuple(
            child.data.path.name
            for child in projects_node.children
            if child.data is not None
        ) == ("api", "docs", "portfolio", "prototype")
        assert tree.cursor_node is not None
        assert tree.cursor_node.data is not None
        assert tree.cursor_node.data.path.name == "api"
        assert str(filter_value.content) == "Type to filter current folder"
        assert not filter_value.has_class("active-filter")


async def test_filter_is_local_and_filtered_directory_can_be_selected(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    projects = tmp_path / "Projects"
    api = projects / "api"
    payments = api / "payments"
    payments.mkdir(parents=True)
    (projects / "docs").mkdir()
    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        working_directory_root=tmp_path,
    )

    async with app.run_test() as pilot:
        modal = await _open_working_directory_modal(app, pilot, "Payments Work")
        tree = modal.query_one(FolderTree)
        await _load_tree(tree)
        projects_node = next(
            child
            for child in tree.root.children
            if child.data is not None and child.data.path.resolve() == projects.resolve()
        )
        tree.move_cursor(projects_node)
        await pilot.press("right")
        await tree._load_queue.join()

        await pilot.press("p", "a", "y")
        await pilot.pause()

        projects_node = next(
            child
            for child in tree.root.children
            if child.data is not None and child.data.path.resolve() == projects.resolve()
        )
        assert not projects_node.children
        assert tree.cursor_node is projects_node

        await pilot.press("backspace", "backspace", "backspace")
        await pilot.pause()
        projects_node = next(
            child
            for child in tree.root.children
            if child.data is not None and child.data.path.resolve() == projects.resolve()
        )
        api_node = next(
            child
            for child in projects_node.children
            if child.data is not None and child.data.path.resolve() == api.resolve()
        )
        tree.move_cursor(api_node)
        await pilot.press("right")
        await tree._load_queue.join()

        await pilot.press("P", "A", "Y")
        await pilot.pause()

        projects_node = next(
            child
            for child in tree.root.children
            if child.data is not None and child.data.path.resolve() == projects.resolve()
        )
        api_node = next(
            child
            for child in projects_node.children
            if child.data is not None and child.data.path.resolve() == api.resolve()
        )
        assert tree.name_filter_directory == api.resolve()
        assert tuple(
            child.data.path.resolve()
            for child in api_node.children
            if child.data is not None
        ) == (payments.resolve(),)
        assert tree.cursor_node is api_node.children[0]
        await pilot.press("enter")
        await pilot.pause()

        session = app.session_manager.active_session
        assert session is not None
        assert session.name == "Payments Work"
        assert session.cwd == payments.resolve()


async def test_enter_with_no_filter_matches_does_not_select_scope_directory(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    projects = tmp_path / "Projects"
    (projects / "AgentHub").mkdir(parents=True)
    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        working_directory_root=tmp_path,
    )

    async with app.run_test() as pilot:
        modal = await _open_working_directory_modal(app, pilot)
        tree = modal.query_one(FolderTree)
        await _load_tree(tree)
        projects_node = next(
            child
            for child in tree.root.children
            if child.data is not None and child.data.path.resolve() == projects.resolve()
        )
        tree.move_cursor(projects_node)
        await pilot.press("right")
        await tree._load_queue.join()

        await pilot.press(*"does-not-exist")
        await pilot.pause()

        assert not tree.has_name_filter_matches
        assert tree.cursor_node is not None
        assert tree.cursor_node.data is not None
        assert tree.cursor_node.data.path.resolve() == projects.resolve()

        await pilot.press("enter")
        await pilot.pause()

        assert app.screen is modal
        assert tree.has_focus
        assert app.session_manager.sessions == ()
        assert not app.query("AgentTerminal")


async def test_filter_query_supports_spaces_in_directory_names(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    matching = tmp_path / "My Project"
    matching.mkdir()
    (tmp_path / "MyProject").mkdir()
    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        working_directory_root=tmp_path,
    )

    async with app.run_test() as pilot:
        modal = await _open_working_directory_modal(app, pilot)
        tree = modal.query_one(FolderTree)
        await _load_tree(tree)

        await pilot.press("M", "y", "space", "P", "r", "o", "j", "e", "c", "t")
        await pilot.pause()

        assert tree.name_filter_directory == tmp_path.resolve()
        assert tree.name_filter_query == "My Project"
        assert tuple(
            child.data.path.resolve()
            for child in tree.root.children
            if child.data is not None
        ) == (matching.resolve(),)
        assert tree.cursor_node is tree.root.children[0]


async def test_right_enters_filtered_directory_with_a_fresh_filter(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    projects = tmp_path / "Projects"
    agenthub = projects / "AgentHub"
    backend = projects / "Backend"
    agenthub.mkdir(parents=True)
    backend.mkdir()
    (tmp_path / "Downloads").mkdir()
    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        working_directory_root=tmp_path,
    )

    async with app.run_test() as pilot:
        modal = await _open_working_directory_modal(app, pilot)
        tree = modal.query_one(FolderTree)
        filter_value = modal.query_one("#working-directory-filter-value", Static)
        await _load_tree(tree)

        await pilot.press(*"Projects")
        await pilot.pause()

        assert tree.name_filter_directory == tmp_path.resolve()
        assert tree.name_filter_query == "Projects"
        assert tree.cursor_node is not None
        assert tree.cursor_node.data is not None
        assert tree.cursor_node.data.path.resolve() == projects.resolve()

        await pilot.press("right")
        await tree._load_queue.join()
        assert tree.cursor_node is not None
        assert tree.cursor_node.data is not None
        assert tree.cursor_node.data.path.resolve() == projects.resolve()
        assert tree.cursor_node.is_expanded

        await pilot.press("right")
        await pilot.pause()

        assert tree.name_filter_directory is None
        assert tree.name_filter_query == ""
        assert tree.cursor_node is not None
        assert tree.cursor_node.data is not None
        assert tree.cursor_node.data.path.resolve() == agenthub.resolve()
        assert str(filter_value.content) == "Type to filter current folder"

        await pilot.press(*"Backend")
        await pilot.pause()

        assert tree.name_filter_directory == projects.resolve()
        assert tree.name_filter_query == "Backend"
        assert tree.cursor_node is not None
        assert tree.cursor_node.data is not None
        assert tree.cursor_node.data.path.resolve() == backend.resolve()
        assert str(filter_value.content) == f"{projects.resolve()}: Backend"


async def test_filter_composes_with_hidden_toggle_and_escape_still_cancels(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    hidden = tmp_path / ".private-project"
    hidden.mkdir()
    (tmp_path / "public-project").mkdir()
    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        working_directory_root=tmp_path,
    )

    async with app.run_test() as pilot:
        modal = await _open_working_directory_modal(app, pilot)
        tree = modal.query_one(FolderTree)
        await _load_tree(tree)

        await pilot.press("p", "r", "i", "v", "a", "t", "e")
        await pilot.pause()

        assert tree.name_filter_directory == tmp_path.resolve()
        assert tree.name_filter_query == "private"
        assert not tree.root.children

        await pilot.press("ctrl+h")
        await pilot.pause()

        assert tree.show_hidden
        assert tree.name_filter_query == "private"
        assert tuple(
            child.data.path.resolve()
            for child in tree.root.children
            if child.data is not None
        ) == (hidden.resolve(),)
        assert tree.cursor_node is tree.root.children[0]

        await pilot.press("escape")
        await pilot.pause()

        assert not isinstance(app.screen, WorkingDirectoryModal)
        assert app.session_manager.sessions == ()


async def test_hiding_active_hidden_filter_scope_clears_filter(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    visible = tmp_path / "visible-project"
    hidden = visible / ".hidden-project"
    (hidden / "Backend").mkdir(parents=True)
    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        working_directory_root=tmp_path,
    )

    async with app.run_test() as pilot:
        modal = await _open_working_directory_modal(app, pilot)
        tree = modal.query_one(FolderTree)
        filter_value = modal.query_one("#working-directory-filter-value", Static)
        await _load_tree(tree)
        await pilot.press("ctrl+h")
        await pilot.pause()

        visible_node = next(
            child
            for child in tree.root.children
            if child.data is not None and child.data.path.resolve() == visible.resolve()
        )
        tree.move_cursor(visible_node)
        await pilot.press("right")
        await tree._load_queue.join()
        hidden_node = next(
            child
            for child in visible_node.children
            if child.data is not None and child.data.path.resolve() == hidden.resolve()
        )
        tree.move_cursor(hidden_node)
        await pilot.press("right")
        await tree._load_queue.join()
        await pilot.press(*"Backend")
        await pilot.pause()

        assert tree.name_filter_directory == hidden.resolve()
        assert tree.name_filter_query == "Backend"

        await pilot.press("ctrl+h")
        await pilot.pause()

        assert not tree.show_hidden
        assert tree.name_filter_directory is None
        assert tree.name_filter_query == ""
        assert tree.cursor_node is not None
        assert tree.cursor_node.data is not None
        assert tree.cursor_node.data.path.resolve() == visible.resolve()
        assert tuple(
            child.data.path.resolve()
            for child in tree.root.children
            if child.data is not None
        ) == (visible.resolve(),)
        visible_node = tree.root.children[0]
        assert not visible_node.children
        assert str(filter_value.content) == "Type to filter current folder"
        assert not filter_value.has_class("active-filter")
        assert tree.has_focus
        assert app.session_manager.sessions == ()


async def test_directory_modal_expands_and_selects_a_nested_folder(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    projects = tmp_path / "Projects"
    project = projects / "AgentHub"
    project.mkdir(parents=True)
    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        working_directory_root=tmp_path,
    )

    async with app.run_test() as pilot:
        modal = await _open_working_directory_modal(app, pilot, "Nested Project")
        tree = modal.query_one(FolderTree)
        await _load_tree(tree)
        projects_node = next(
            node
            for node in tree.root.children
            if node.data is not None and node.data.path.resolve() == projects.resolve()
        )

        tree.move_cursor(projects_node)
        await pilot.press("right")
        await tree._load_queue.join()
        project_node = next(
            node
            for node in projects_node.children
            if node.data is not None and node.data.path.resolve() == project.resolve()
        )
        assert projects_node.is_expanded
        assert tree.cursor_node is projects_node

        await pilot.press("right")
        assert tree.cursor_node is project_node

        await pilot.press("left")
        assert tree.cursor_node is projects_node
        assert projects_node.is_expanded

        await pilot.press("left")
        assert tree.cursor_node is projects_node
        assert not projects_node.is_expanded

        await pilot.press("right")
        assert projects_node.is_expanded
        assert tree.cursor_node is projects_node

        await pilot.press("right")
        assert tree.cursor_node is project_node

        await pilot.press("enter")
        await pilot.pause()

        session = app.session_manager.active_session
        assert session is not None
        assert session.cwd == project.resolve()


async def test_selected_directory_creates_and_focuses_named_agent(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    project = tmp_path / "agenthub"
    project.mkdir()
    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        working_directory_root=tmp_path,
    )
    original_cwd = Path.cwd()

    async with app.run_test() as pilot:
        await _open_working_directory_modal(app, pilot, "  AgentHub Refactor  ")
        await _confirm_directory(app, pilot, project)

        sessions = app.session_manager.sessions
        assert len(sessions) == 1
        session = sessions[0]
        assert session.kind is SessionKind.AGENT
        assert session.name == "AgentHub Refactor"
        assert session.harness is sleeping_harness
        assert session.cwd == project.resolve()
        assert session.terminal.working_directory == project.resolve()
        assert session.terminal.is_mounted
        assert session.terminal.has_focus
        assert app.session_manager.active_session is session
        assert app.query_one(SessionSidebar).visible_session_ids == (session.id,)
        assert app.query_one("#session-content", ContentSwitcher).current == (
            app._terminal_dom_id(session.id)
        )
        assert Path.cwd() == original_cwd


async def test_selected_directory_reaches_the_actual_child_process(tmp_path: Path) -> None:
    project = tmp_path / "backend"
    project.mkdir()
    marker = tmp_path / "child-cwd.txt"
    harness = AgentHarness(
        id="cwd-reporter",
        display_name="CWD Reporter",
        command=(
            sys.executable,
            "-c",
            (
                "import pathlib, sys, time; "
                "pathlib.Path(sys.argv[1]).write_text(str(pathlib.Path.cwd())); "
                "time.sleep(30)"
            ),
            str(marker),
        ),
        scroll=None,
    )
    app = AgentHubApp(
        agent_harnesses={harness.id: harness},
        working_directory_root=tmp_path,
    )
    original_cwd = Path.cwd()

    async with app.run_test() as pilot:
        await _open_working_directory_modal(app, pilot, "Backend Work")
        await _confirm_directory(app, pilot, project)
        for _ in range(20):
            if marker.exists():
                break
            await pilot.pause(0.05)

        assert marker.read_text() == str(project.resolve())
        assert Path.cwd() == original_cwd


async def test_multiple_harness_navigation_connects_selection_to_named_session(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    harness_a = replace(sleeping_harness, id="harness-a", display_name="Harness A")
    harness_b = replace(sleeping_harness, id="harness-b", display_name="Harness B")
    app = AgentHubApp(
        agent_harnesses={
            harness_a.id: harness_a,
            harness_b.id: harness_b,
        },
        working_directory_root=tmp_path,
    )

    async with app.run_test() as pilot:
        await pilot.press("ctrl+n")
        harness_list = app.screen.query_one("#harness-selection-list", OptionList)
        await pilot.press("down")
        assert harness_list.highlighted == 1

        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, SessionNameModal)
        assert str(app.screen.query_one("#session-name-harness", Static).content) == (
            "Harness: Harness B"
        )
        assert app.session_manager.sessions == ()

        app.screen.query_one("#session-name-input", Input).value = "Backend Work"
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, WorkingDirectoryModal)
        await _confirm_directory(app, pilot, tmp_path)
        session = app.session_manager.active_session
        assert session is not None
        assert session.harness is harness_b
        assert session.harness.id == "harness-b"
        assert session.name == "Backend Work"
        assert session.cwd == tmp_path.resolve()


async def test_cancelling_name_with_existing_terminal_preserves_runtime(
    sleeping_harness: AgentHarness,
) -> None:
    app = AgentHubApp(agent_harnesses={sleeping_harness.id: sleeping_harness})
    existing = app.session_manager.create(
        name="Existing Agent",
        kind=SessionKind.AGENT,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )

    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_name_modal(app, pilot)
        assert existing.terminal.is_mounted
        assert existing.terminal.is_process_running

        await pilot.press("escape")
        await pilot.pause()

        assert app.session_manager.sessions == (existing,)
        assert app.session_manager.active_session is existing
        assert existing.terminal.is_mounted
        assert existing.terminal.is_process_running
        assert existing.terminal.has_focus
        assert not app.hub_locked


async def test_cancelling_directory_with_existing_terminal_preserves_runtime(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        working_directory_root=tmp_path,
    )
    existing = app.session_manager.create(
        name="Existing Agent",
        kind=SessionKind.AGENT,
        cwd=tmp_path,
        harness=sleeping_harness,
    )

    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_working_directory_modal(app, pilot, "Cancelled Agent")

        assert existing.terminal.is_mounted
        assert existing.terminal.is_process_running
        pty = existing.terminal.board.pty
        assert pty is not None
        with patch.object(pty, "write", wraps=pty.write) as write_spy:
            await pilot.press("p")
            await pilot.pause()

        assert app.screen.query_one(FolderTree).name_filter_query == "p"
        write_spy.assert_not_called()

        await pilot.press("escape")
        await pilot.pause()

        assert app.session_manager.sessions == (existing,)
        assert app.session_manager.active_session is existing
        assert existing.terminal.is_mounted
        assert existing.terminal.is_process_running
        assert existing.terminal.has_focus


async def test_successful_second_session_keeps_existing_terminal_alive(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    first_directory = tmp_path / "first"
    second_directory = tmp_path / "second"
    first_directory.mkdir()
    second_directory.mkdir()
    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        working_directory_root=tmp_path,
    )
    existing = app.session_manager.create(
        name="Agent A",
        kind=SessionKind.AGENT,
        cwd=first_directory,
        harness=sleeping_harness,
    )

    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_working_directory_modal(app, pilot, "Agent B")
        assert existing.terminal.is_mounted
        assert existing.terminal.is_process_running
        await _confirm_directory(app, pilot, second_directory)

        sessions = app.session_manager.sessions
        assert len(sessions) == 2
        created = sessions[1]
        assert existing.cwd == first_directory.resolve()
        assert created.cwd == second_directory.resolve()
        assert existing.terminal.is_mounted
        assert existing.terminal.is_process_running
        assert created.terminal.is_mounted
        assert created.terminal.is_process_running
        assert app.session_manager.active_session is created
        assert created.terminal.has_focus
        assert app.query_one(SessionSidebar).visible_session_ids == (
            existing.id,
            created.id,
        )


async def test_agent_creation_mount_failure_rolls_back_to_previous_session(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        working_directory_root=tmp_path,
    )
    creation_error: Exception | None = None
    create_session = app._on_working_directory_selected

    async def capture_creation_error(
        harness: AgentHarness,
        name: str,
        cwd: Path | None,
    ) -> None:
        nonlocal creation_error
        try:
            await create_session(harness, name, cwd)
        except RuntimeError as error:
            creation_error = error

    app._on_working_directory_selected = capture_creation_error  # type: ignore[method-assign]
    existing = app.session_manager.create(
        name="Existing Agent",
        kind=SessionKind.AGENT,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )

    original_cwd = Path.cwd()
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_working_directory_modal(app, pilot, "Failed Agent")
        switcher = app.query_one("#session-content", ContentSwitcher)
        with patch.object(
            switcher,
            "mount",
            new=AsyncMock(side_effect=RuntimeError("mount failed")),
        ):
            await _confirm_directory(app, pilot, tmp_path)

        assert isinstance(creation_error, RuntimeError)
        assert str(creation_error) == "mount failed"
        assert app.session_manager.sessions == (existing,)
        assert app.session_manager.active_session is existing
        assert app.query_one(SessionSidebar).visible_session_ids == (existing.id,)
        assert switcher.current == app._terminal_dom_id(existing.id)
        assert existing.terminal.is_mounted
        assert existing.terminal.is_process_running
        assert Path.cwd() == original_cwd
