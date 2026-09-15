"""Working-directory selection for the New Agent Session workflow."""

import asyncio
from collections.abc import Iterable
from pathlib import Path
from typing import ClassVar

from textual import events, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import DirectoryTree, Label, Static, Tree
from textual.widgets.tree import TreeNode
from textual.worker import get_current_worker


def _format_display_path(path: Path) -> str:
    """Format a path for display, abbreviating locations below home."""

    home = Path.home().expanduser().resolve()
    resolved = path.expanduser().resolve()
    try:
        relative = resolved.relative_to(home)
    except ValueError:
        return str(resolved)
    return "~" if relative == Path() else f"~/{relative}"


class FolderTree(DirectoryTree):
    """DirectoryTree variant that displays folders only."""

    class NameFilterChanged(Message):
        """Notify the picker when the tree's local name filter changes."""

    BINDINGS: ClassVar = [
        Binding("left", "collapse_or_parent", show=False),
        Binding("right", "expand_or_child", show=False),
    ]

    def __init__(
        self,
        path: str | Path,
        *,
        show_hidden: bool = False,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
    ) -> None:
        """Create a folder tree with dot-prefixed directories hidden by default."""

        self.show_hidden = show_hidden
        self._name_filter_directory: Path | None = None
        self._name_filter_query = ""
        super().__init__(
            path,
            name=name,
            id=id,
            classes=classes,
            disabled=disabled,
        )

    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        """Remove files, inaccessible entries, and optionally hidden folders."""

        return (
            path
            for path in paths
            if self._safe_is_dir(path)
            and (self.show_hidden or not path.name.startswith("."))
        )

    @property
    def name_filter_directory(self) -> Path | None:
        """Return the directory whose immediate children are being filtered."""

        return self._name_filter_directory

    @property
    def name_filter_query(self) -> str:
        """Return the current case-insensitive directory-name query."""

        return self._name_filter_query

    def filter_scope_for_cursor(self) -> Path:
        """Resolve the directory level that owns the current cursor position."""

        node = self.cursor_node or self.root
        if node.data is None:
            return self.path.expanduser().resolve()
        if node.is_expanded or node.parent is None or node.parent.data is None:
            return node.data.path.expanduser().resolve()
        return node.parent.data.path.expanduser().resolve()

    async def set_name_filter(self, *, directory: Path, query: str) -> None:
        """Set a local name filter and reload while preserving tree state."""

        self._name_filter_query = query
        self._name_filter_directory = (
            directory.expanduser().resolve() if query else None
        )
        await self.reload()
        self.focus_first_name_filter_match()
        self.post_message(self.NameFilterChanged())

    def focus_first_name_filter_match(self) -> None:
        """Focus the first match, or the filter scope when nothing matches."""

        if not self._name_filter_query or self._name_filter_directory is None:
            return
        scope_node = self._find_loaded_node(self._name_filter_directory)
        if scope_node is not None:
            self.move_cursor(scope_node.children[0] if scope_node.children else scope_node)

    def _find_loaded_node(self, path: Path) -> TreeNode | None:
        """Find a currently loaded tree node by normalized filesystem path."""

        target = path.expanduser().resolve()
        to_check = [self.root]
        while to_check:
            node = to_check.pop()
            if node.data is not None and node.data.path.expanduser().resolve() == target:
                return node
            to_check.extend(reversed(node.children))
        return None

    @work(exit_on_error=False)
    async def _load_directory(self, node: TreeNode) -> list[Path]:
        """Load one directory without Textual's leaking default-executor worker.

        Textual 8.2.8 runs this method in the event loop's default executor.
        Under the project's Python 3.13 runtime, cancelling or completing that
        worker can leave the executor unable to shut down after the picker has
        been mounted. Keep Textual's queue, error handling, and tree population,
        but perform the small directory scan cooperatively on the event loop.
        Lifecycle integration tests protect this version-sensitive override.
        """

        assert node.data is not None
        path = node.data.path.expanduser().resolve()
        worker = get_current_worker()
        content: list[Path] = []
        normalized_query = self._name_filter_query.casefold()
        for entry in self.filter_paths(self._directory_content(path, worker)):
            if (
                normalized_query
                and path == self._name_filter_directory
                and normalized_query not in entry.name.casefold()
            ):
                continue
            content.append(entry)
            await asyncio.sleep(0)
        return sorted(content, key=lambda entry: entry.name.lower())

    async def _on_tree_node_expanded(self, event: Tree.NodeExpanded) -> None:
        """Load expanded folders without entering the default executor."""

        event.prevent_default()
        event.stop()
        data = event.node.data
        if data is None:
            return
        if self._safe_is_dir(data.path):
            await self._add_to_load_queue(event.node)
        else:
            self.post_message(self.FileSelected(event.node, data.path))

    async def _on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        """Publish native selection messages without entering the executor."""

        event.prevent_default()
        event.stop()
        data = event.node.data
        if data is None:
            return
        if self._safe_is_dir(data.path):
            self.post_message(self.DirectorySelected(event.node, data.path))
        else:
            self.post_message(self.FileSelected(event.node, data.path))

    def action_collapse_or_parent(self) -> None:
        """Collapse an expanded folder, or move to its parent."""

        node = self.cursor_node
        if node is None:
            return
        if node.is_expanded:
            node.collapse()
            return
        if node.parent is None:
            return
        self.move_cursor(node.parent)

    async def action_expand_or_child(self) -> None:
        """Expand a folder, or focus its first child when already expanded."""

        node = self.cursor_node
        if node is None or not node.allow_expand:
            return
        if self._name_filter_query:
            data = node.data
            if data is None:
                return
            target_path = data.path.expanduser().resolve()
            await self.set_name_filter(directory=target_path, query="")
            node = self._find_loaded_node(target_path)
            if node is None:
                return
        if not node.is_expanded:
            node.expand()
            await self._add_to_load_queue(node)
            return
        if node.children:
            self.move_cursor(node.children[0])


class WorkingDirectoryModal(ModalScreen[Path]):
    """Collect a normalized working directory without creating a runtime."""

    CSS_PATH = "working_directory.tcss"
    BINDINGS: ClassVar = [
        Binding("ctrl+h", "toggle_hidden", show=False),
        Binding("escape", "cancel", show=False),
    ]

    def __init__(self, *, root: Path | None = None) -> None:
        """Create a directory picker rooted at ``root``."""

        super().__init__()
        self._root = (Path.home() if root is None else root).expanduser().resolve()
        self._selected_directory: Path | None = None

    @property
    def selected_directory(self) -> Path | None:
        """Return the confirmed directory, or ``None`` before confirmation."""

        return self._selected_directory

    def compose(self) -> ComposeResult:
        """Compose the directory tree, selection preview, and help text."""

        with Vertical(id="working-directory-dialog"):
            with Horizontal(id="working-directory-header"):
                yield Label(
                    "Choose Working Directory",
                    id="working-directory-title",
                )
                with Horizontal(
                    id="working-directory-cancel",
                    classes="modal-cancel",
                ):
                    yield Static(
                        "Esc",
                        classes="modal-shortcut-key modal-cancel-key",
                    )
                    yield Static(
                        "Cancel",
                        classes="modal-shortcut-description modal-cancel-description",
                    )
            yield FolderTree(self._root, id="working-directory-tree")
            with Horizontal(id="working-directory-selected-row"):
                yield Label("Selected", id="working-directory-selected-label")
                yield Static(
                    _format_display_path(self._root),
                    id="working-directory-selected-path",
                )
            with Horizontal(id="working-directory-filter-row"):
                yield Label("Filter", id="working-directory-filter-label")
                yield Static(
                    "Type to filter current folder",
                    id="working-directory-filter-value",
                )
            with Grid(id="working-directory-help", classes="modal-shortcut-grid"):
                yield Static("↑/↓", classes="modal-shortcut-key")
                yield Static("Navigate", classes="modal-shortcut-description")
                yield Static("←", classes="modal-shortcut-key")
                yield Static(
                    "Collapse / Parent",
                    classes="modal-shortcut-description",
                )
                yield Static("→", classes="modal-shortcut-key")
                yield Static(
                    "Expand / First Child",
                    classes="modal-shortcut-description",
                )
                yield Static("Enter", classes="modal-shortcut-key")
                yield Static("Select", classes="modal-shortcut-description")
                yield Static("Ctrl+H", classes="modal-shortcut-key")
                yield Static(
                    self._hidden_help_text(show_hidden=False),
                    id="working-directory-hidden-help",
                    classes="modal-shortcut-description",
                )
                yield Static("Type", classes="modal-shortcut-key")
                yield Static("Filter", classes="modal-shortcut-description")
                yield Static("Backspace", classes="modal-shortcut-key")
                yield Static("Edit Filter", classes="modal-shortcut-description")

    def on_mount(self) -> None:
        """Give native tree navigation immediate keyboard focus."""

        self.query_one(FolderTree).focus()

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted) -> None:
        """Preview the directory under the native tree cursor."""

        data = event.node.data
        if data is not None:
            self.query_one("#working-directory-selected-path", Static).update(
                _format_display_path(data.path)
            )

    def on_folder_tree_name_filter_changed(
        self,
        event: FolderTree.NameFilterChanged,
    ) -> None:
        """Keep the visible filter state synchronized with tree navigation."""

        event.stop()
        self._update_filter_status(self.query_one(FolderTree))

    async def on_key(self, event: events.Key) -> None:
        """Turn unmodified printable keys into a local directory-name filter."""

        tree = self.query_one(FolderTree)
        if not tree.has_focus:
            return

        if event.key == "backspace":
            if not tree.name_filter_query:
                return
            event.prevent_default()
            event.stop()
            await tree.set_name_filter(
                directory=tree.name_filter_directory or tree.path,
                query=tree.name_filter_query[:-1],
            )
            tree.focus()
            return

        character = event.character
        if (
            not event.is_printable
            or character is None
            or character.isspace()
            or event.key.startswith(("ctrl+", "alt+", "meta+", "super+"))
        ):
            return

        event.prevent_default()
        event.stop()
        directory = tree.name_filter_directory or tree.filter_scope_for_cursor()
        query = tree.name_filter_query
        await tree.set_name_filter(directory=directory, query=f"{query}{character}")
        tree.focus()

    def on_directory_tree_directory_selected(
        self,
        event: DirectoryTree.DirectorySelected,
    ) -> None:
        """Confirm the authoritative DirectoryTree selection as a real Path."""

        event.stop()
        selected_directory = event.path.expanduser().resolve()
        self._selected_directory = selected_directory
        self.query_one("#working-directory-selected-path", Static).update(
            _format_display_path(selected_directory)
        )
        self.dismiss(selected_directory)

    async def action_toggle_hidden(self) -> None:
        """Toggle dot-prefixed directories and preserve the current tree state."""

        tree = self.query_one(FolderTree)
        tree.show_hidden = not tree.show_hidden
        await tree.reload()
        tree.focus_first_name_filter_match()
        self.query_one("#working-directory-hidden-help", Static).update(
            self._hidden_help_text(show_hidden=tree.show_hidden)
        )
        tree.focus()

    def _update_filter_status(self, tree: FolderTree) -> None:
        """Reflect the active local query and its directory scope in the UI."""

        filter_value = self.query_one("#working-directory-filter-value", Static)
        if tree.name_filter_query and tree.name_filter_directory is not None:
            filter_value.update(
                f"{_format_display_path(tree.name_filter_directory)}: "
                f"{tree.name_filter_query}"
            )
            filter_value.add_class("active-filter")
        else:
            filter_value.update("Type to filter current folder")
            filter_value.remove_class("active-filter")

    @staticmethod
    def _hidden_help_text(*, show_hidden: bool) -> str:
        """Build the shortcut line for the current hidden-directory action."""

        return "Hide Hidden" if show_hidden else "Show Hidden"

    def action_cancel(self) -> None:
        """Cancel the workflow without creating a session."""

        self.dismiss(None)
