"""Unit coverage for working-directory presentation and filtering."""

from pathlib import Path
from unittest.mock import patch

from agenthub.presentation.modals.working_directory import (
    FolderTree,
    WorkingDirectoryModal,
    _format_display_path,
)


def test_format_display_path_abbreviates_home_and_descendants(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = home / "Projects" / "AgentHub"
    outside = tmp_path / "outside"
    project.mkdir(parents=True)
    outside.mkdir()

    with patch("pathlib.Path.home", return_value=home):
        assert _format_display_path(home) == "~"
        assert _format_display_path(project) == "~/Projects/AgentHub"
        assert _format_display_path(outside) == str(outside.resolve())


def test_folder_tree_filters_out_files_and_hidden_directories_by_default(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    hidden = tmp_path / ".hidden"
    file_path = tmp_path / "README.md"
    first.mkdir()
    second.mkdir()
    hidden.mkdir()
    file_path.touch()
    tree = FolderTree.__new__(FolderTree)
    tree.show_hidden = False

    paths = (first, hidden, file_path, second)

    assert tuple(tree.filter_paths(paths)) == (first, second)

    tree.show_hidden = True

    assert tuple(tree.filter_paths(paths)) == (first, hidden, second)


def test_working_directory_modal_retains_normalized_root_without_selection(
    tmp_path: Path,
) -> None:
    modal = WorkingDirectoryModal(root=tmp_path / ".." / tmp_path.name)

    assert modal._root == tmp_path.resolve()
    assert modal.selected_directory is None
