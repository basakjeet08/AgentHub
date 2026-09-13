"""Integration coverage for AgentHub's styled Textual command palette."""

import pytest
from textual.command import CommandList, CommandPalette

from agenthub.app import AgentHubApp


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


async def test_command_palette_calls_textual_keys_help_shortcuts() -> None:
    app = AgentHubApp()

    async with app.run_test(size=(100, 36)) as pilot:
        await pilot.press("ctrl+p")
        await app.workers.wait_for_complete()
        await pilot.pause()

        command_list = app.screen.query_one(CommandList)
        command_titles = [str(option.prompt).splitlines()[0] for option in command_list.options]

        assert "Shortcuts" in command_titles
        assert "Keys" not in command_titles
