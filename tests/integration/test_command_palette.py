"""Integration coverage for AgentHub's styled Textual command palette."""

import pytest
from textual.command import CommandList, CommandPalette

from agenthub.app import AgentHubApp

PALETTE_COMMAND_TITLES = {
    "New Agent",
    "New Shell",
    "Refresh Native Sessions",
    "Open Session",
    "Quit AgentHub",
    "Shortcuts",
}


@pytest.mark.parametrize("size", [(100, 36), (60, 20), (40, 15)])
async def test_command_palette_is_centered_and_contained(
    size: tuple[int, int],
) -> None:
    app = AgentHubApp()

    async with app.run_test(size=size) as pilot:
        await pilot.press("ctrl+p")
        await app.workers.wait_for_complete()
        await pilot.pause()

        palette = app.screen
        assert isinstance(palette, CommandPalette)

        input_region = palette.query_one("#--input").region
        results_region = palette.query_one(CommandList).region
        expected_width = min(80, max(36, size[0] // 2))

        assert input_region.width == expected_width
        assert results_region.width == expected_width
        assert abs((input_region.x * 2 + input_region.width) - size[0]) <= 1

        modal_top = input_region.y
        modal_bottom = results_region.y + results_region.height
        assert modal_top >= 0
        assert modal_bottom <= size[1]
        assert abs((modal_top + modal_bottom) - size[1]) <= 1

        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, CommandPalette)


async def test_command_palette_exposes_agenthub_actions() -> None:
    app = AgentHubApp()

    async with app.run_test(size=(100, 36)) as pilot:
        await pilot.press("ctrl+p")
        await app.workers.wait_for_complete()
        await pilot.pause()

        command_list = app.screen.query_one(CommandList)
        command_titles = [str(option.prompt).splitlines()[0] for option in command_list.options]

        assert PALETTE_COMMAND_TITLES <= set(command_titles)
        assert "Keys" not in command_titles
        assert "Quit" not in command_titles
        assert command_titles.count("Shortcuts") == 1
        assert command_titles.count("Quit AgentHub") == 1


async def test_command_palette_callbacks_reuse_existing_actions() -> None:
    app = AgentHubApp()

    async with app.run_test():
        commands = {
            command.title: command for command in app.get_system_commands(app.screen)
        }

        assert commands["New Agent"].callback == app.action_new_session
        assert commands["New Shell"].callback == app.action_new_shell
        assert commands["Refresh Native Sessions"].callback == app.action_resync_sessions
        assert commands["Open Session"].callback == app.action_open_session
        assert "Focus Agents" not in commands
        assert "Focus Shells" not in commands
        assert commands["Quit AgentHub"].callback == app.action_quit
        assert commands["Shortcuts"].callback == app.action_show_help_panel
