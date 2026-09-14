"""Integration coverage for the two-stage New Agent Session workflow."""

from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from textual.command import CommandPalette
from textual.pilot import Pilot
from textual.widgets import ContentSwitcher, Input, Label, OptionList, Static

from agenthub.app import AgentHubApp
from agenthub.harnesses import HARNESSES, AgentHarness
from agenthub.sessions import SessionKind
from agenthub.ui import HomeScreen, SessionSidebar
from agenthub.ui.modals import HarnessSelectionModal, SessionNameModal


async def _open_name_modal(app: AgentHubApp, pilot: Pilot) -> SessionNameModal:
    """Select the currently highlighted harness without creating a runtime."""

    await pilot.press("ctrl+n")
    await pilot.press("enter")
    await pilot.pause()
    assert isinstance(app.screen, SessionNameModal)
    return app.screen


async def _submit_name(app: AgentHubApp, pilot: Pilot, name: str) -> None:
    """Set and submit the visible session-name input."""

    app.screen.query_one("#session-name-input", Input).value = name
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
        assert not app.screen.query("#harness-selection-prompt")
        assert tuple((option.id, str(option.prompt)) for option in harness_list.options) == tuple(
            (harness.id, harness.display_name) for harness in HARNESSES.values()
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


async def test_escape_from_name_modal_cancels_the_entire_workflow(
    sleeping_harness: AgentHarness,
) -> None:
    app = AgentHubApp(agent_harnesses={sleeping_harness.id: sleeping_harness})

    async with app.run_test() as pilot:
        await _open_name_modal(app, pilot)
        await pilot.press("escape")
        await pilot.pause()

        assert not isinstance(app.screen, (HarnessSelectionModal, SessionNameModal))
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


async def test_valid_trimmed_name_creates_and_focuses_selected_agent(
    sleeping_harness: AgentHarness,
) -> None:
    app = AgentHubApp(agent_harnesses={sleeping_harness.id: sleeping_harness})

    async with app.run_test() as pilot:
        await _open_name_modal(app, pilot)
        await _submit_name(app, pilot, "  AgentHub Refactor  ")

        sessions = app.session_manager.sessions
        assert len(sessions) == 1
        session = sessions[0]
        assert session.kind is SessionKind.AGENT
        assert session.name == "AgentHub Refactor"
        assert session.harness is sleeping_harness
        assert session.terminal.is_mounted
        assert session.terminal.has_focus
        assert app.session_manager.active_session is session
        assert app.query_one(SessionSidebar).visible_session_ids == (session.id,)
        assert app.query_one("#session-content", ContentSwitcher).current == (
            app._terminal_dom_id(session.id)
        )


async def test_multiple_harness_navigation_connects_selection_to_named_session(
    sleeping_harness: AgentHarness,
) -> None:
    harness_a = replace(sleeping_harness, id="harness-a", display_name="Harness A")
    harness_b = replace(sleeping_harness, id="harness-b", display_name="Harness B")
    app = AgentHubApp(
        agent_harnesses={
            harness_a.id: harness_a,
            harness_b.id: harness_b,
        }
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

        await _submit_name(app, pilot, "Backend Work")
        session = app.session_manager.active_session
        assert session is not None
        assert session.harness is harness_b
        assert session.harness.id == "harness-b"
        assert session.name == "Backend Work"


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


async def test_successful_second_session_keeps_existing_terminal_alive(
    sleeping_harness: AgentHarness,
) -> None:
    app = AgentHubApp(agent_harnesses={sleeping_harness.id: sleeping_harness})
    existing = app.session_manager.create(
        name="Agent A",
        kind=SessionKind.AGENT,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )

    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_name_modal(app, pilot)
        await _submit_name(app, pilot, "Agent B")

        sessions = app.session_manager.sessions
        assert len(sessions) == 2
        created = sessions[1]
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
        switcher = app.query_one("#session-content", ContentSwitcher)
        with patch.object(
            switcher,
            "mount",
            new=AsyncMock(side_effect=RuntimeError("mount failed")),
        ), pytest.raises(RuntimeError, match="mount failed"):
            await app._create_agent_session(
                harness=sleeping_harness,
                name="Failed Agent",
            )

        assert app.session_manager.sessions == (existing,)
        assert app.session_manager.active_session is existing
        assert app.query_one(SessionSidebar).visible_session_ids == (existing.id,)
        assert switcher.current == app._terminal_dom_id(existing.id)
        assert existing.terminal.is_mounted
        assert existing.terminal.is_process_running
