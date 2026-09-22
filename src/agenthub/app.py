"""Application shell: Home layout, key bindings, and widget orchestration."""

import asyncio
from collections.abc import Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import ClassVar

from textual.app import App, ComposeResult, SystemCommand
from textual.command import CommandPalette
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen, Screen
from textual.widgets import ContentSwitcher

from agenthub.activity import (
    ActivityService,
    AgentActivity,
    AgentActivityEvent,
    AgentActivityEventKind,
)
from agenthub.harnesses import FISH, AgentHarness
from agenthub.native_sessions import (
    NativeSession,
    NativeSessionDeletionError,
    NativeSessionDeletionUnavailableError,
    NativeSessionService,
)
from agenthub.notifications import (
    DesktopNotificationBackend,
    DesktopNotificationService,
)
from agenthub.presentation import (
    AgentHubStatusBar,
    HomeScreen,
    SessionSidebar,
)
from agenthub.presentation.key_bindings import APPLICATION_BINDINGS, TERMINAL_GATED_ACTIONS
from agenthub.presentation.modals import (
    HarnessPickerModal,
    SessionDeleteConfirmationModal,
    SessionLinkModal,
    SessionPickerModal,
    ShellSessionNameInputModal,
    WorkingDirectoryPickerModal,
)
from agenthub.providers import ACTIVITY_ADAPTERS, HARNESSES, NATIVE_SESSION_ADAPTERS
from agenthub.sessions import AgentSession, SessionKind, SessionManager, SessionState
from agenthub.terminal import AgentTerminal

_SESSION_WORKFLOW_MODALS = (
    HarnessPickerModal,
    SessionPickerModal,
    SessionDeleteConfirmationModal,
    SessionLinkModal,
    ShellSessionNameInputModal,
    WorkingDirectoryPickerModal,
)

_FRESH_AGENT_NAME = "New session"


@dataclass(frozen=True)
class _DiscoveryResult:
    """Sessions or failure details returned by one provider discovery."""

    sessions: tuple[NativeSession, ...] = ()
    error: str | None = None


class AgentHubApp(App):
    """Fullscreen AgentHub shell for Home and managed terminal sessions."""

    hub_locked: reactive[bool] = reactive(False, bindings=True)

    CSS_PATH: ClassVar[list[str]] = [
        "presentation/styles/theme.tcss",
        "presentation/styles/app.tcss",
        "presentation/styles/screens/home.tcss",
        "presentation/styles/panels/sidebar.tcss",
        "presentation/styles/panels/status_bar.tcss",
    ]

    BINDINGS: ClassVar = list(APPLICATION_BINDINGS)

    def __init__(
        self,
        *,
        agent_harnesses: Mapping[str, AgentHarness] | None = None,
        shell_harness: AgentHarness = FISH,
        native_session_service: NativeSessionService | None = None,
        working_directory_root: Path | None = None,
        desktop_notification_backend: DesktopNotificationBackend | None = None,
    ) -> None:
        """Create the AgentHub shell without launching a coding harness."""

        super().__init__()
        self.theme = "tokyo-night"
        self.session_manager = SessionManager()
        self._agent_harnesses = dict(
            HARNESSES if agent_harnesses is None else agent_harnesses
        )
        self._shell_harness = shell_harness
        self._native_session_service = native_session_service or NativeSessionService(
            NATIVE_SESSION_ADAPTERS
        )
        self._working_directory_root = (
            Path.home() if working_directory_root is None else working_directory_root
        )
        self._discovery_executor: ThreadPoolExecutor | None = None
        self._discovery_executors: set[ThreadPoolExecutor] = set()
        self._discovery_in_progress = False
        self._provider_locks: dict[str, asyncio.Lock] = {}
        self._command_palette_target_id: str | None = None
        self._activity_service = ActivityService(ACTIVITY_ADAPTERS, self._on_activity_event)
        self._notification_service = DesktopNotificationService(
            backend=desktop_notification_backend
        )

    def compose(self) -> ComposeResult:
        """Compose persistent application chrome and the current main content."""

        sessions = self.session_manager.sessions
        active_session = self.session_manager.active_session
        for session in sessions:
            if session.terminal is not None:
                session.terminal.id = self._terminal_dom_id(session.id)

        initial = (
            self._terminal_dom_id(active_session.id)
            if active_session is not None and active_session.terminal is not None
            else "home-screen"
        )
        with Vertical(id="app-shell"):
            with Horizontal(id="application-body"):
                yield SessionSidebar(
                    sessions,
                    harnesses=self._agent_harnesses.values(),
                    id="session-sidebar",
                )
                yield ContentSwitcher(
                    HomeScreen(id="home-screen"),
                    *(
                        session.terminal
                        for session in sessions
                        if session.terminal is not None
                    ),
                    initial=initial,
                    id="session-content",
                )
            yield AgentHubStatusBar(
                session_count=len(sessions),
                running_count=0,
                locked=self.hub_locked,
                id="status-bar",
            )

    def on_mount(self) -> None:
        """Focus the terminal once mounted so keystrokes reach the agent."""

        session = self.session_manager.active_session
        if session is not None:
            self.show_session(session.id)
        else:
            self.query_one(HomeScreen).focus()
        self.call_after_refresh(self._refresh_status)
        self._start_native_session_discovery()

    async def on_unmount(self) -> None:
        """Stop accepting discovery work when the application is unmounted."""

        for executor in tuple(self._discovery_executors):
            self._shutdown_discovery_executor(executor)
        await self._activity_service.close()
        await self._notification_service.shutdown()

    @staticmethod
    def _terminal_dom_id(session_id: str) -> str:
        """Map application identity to Textual identity at the UI boundary."""

        return f"terminal-{session_id}"

    def show_session(self, session_id: str) -> AgentSession:
        """Select, display, and focus one managed session."""

        session = self.session_manager.get(session_id)
        if session.terminal is None:
            raise ValueError(f"session {session_id!r} is unloaded")
        self.session_manager.select(session_id)
        self.query_one("#session-content", ContentSwitcher).current = self._terminal_dom_id(
            session.id
        )
        sidebar = self.query_one(SessionSidebar)
        sidebar.set_active(session.id)
        sidebar.move_cursor_to_session(session.id)
        self.call_after_refresh(self._highlight_active_sidebar)
        self.set_focus(session.terminal)
        self._apply_activity_event(
            AgentActivityEvent(
                session_id=session.id,
                kind=AgentActivityEventKind.ATTENTION_ACKNOWLEDGED,
            )
        )
        return session

    async def activate_session(self, session_id: str) -> AgentSession:
        """Show a running session or resume and mount an unloaded native one."""

        session = self.session_manager.get(session_id)
        if session.terminal is not None:
            return self.show_session(session.id)
        if session.state is not SessionState.UNLOADED:
            return session
        if session.kind is not SessionKind.AGENT or session.native_session_id is None:
            raise ValueError(f"session {session_id!r} cannot be resumed")

        session.state = SessionState.STARTING
        self._refresh_sidebar()
        native_session = NativeSession(
            harness_id=session.harness.id,
            native_session_id=session.native_session_id,
            name=session.name,
            cwd=session.cwd,
        )
        terminal: AgentTerminal | None = None
        try:
            launch = await self._native_session_service.resume(native_session)
            terminal = AgentTerminal(
                session.harness,
                command=launch.command,
                working_directory=launch.working_directory,
            )
            terminal.id = self._terminal_dom_id(session.id)
            self.session_manager.attach_terminal(session.id, terminal)
            activity_tracking_ready = await self._prepare_activity_tracking(session, terminal)
            await self.query_one("#session-content", ContentSwitcher).mount(terminal)
            if activity_tracking_ready:
                self._initialize_mounted_activity(session)
        except Exception as error:  # noqa: BLE001 - isolate provider/runtime boundary
            self._revoke_activity_tracking(session.id)
            if session.terminal is terminal:
                self.session_manager.detach_terminal(session.id)
            else:
                session.state = SessionState.UNLOADED
            self._refresh_sidebar()
            self._refresh_status()
            self.notify(
                f"Could not resume {session.name}: {error}",
                severity="error",
            )
            return session

        self._refresh_sidebar()
        self._refresh_status()
        return self.show_session(session.id)

    async def _discover_native_sessions(self) -> None:
        """Run one discovery cycle and always release its scheduling guard."""

        try:
            await self._run_native_session_discovery()
        finally:
            self._discovery_in_progress = False

    async def _run_native_session_discovery(self) -> None:
        """Discover each provider independently without blocking app startup."""

        providers = tuple(
            (harness_id, harness)
            for harness_id in self._native_session_service.harness_ids
            if (harness := self._agent_harnesses.get(harness_id)) is not None
        )
        if not providers:
            return

        self.notify(
            "Discovering sessions…",
            title="Session discovery",
            markup=False,
        )
        executor = self._create_discovery_executor(max_workers=min(4, len(providers)))
        try:
            discoveries = await asyncio.gather(
                *(
                    self._discover_and_reconcile_provider(harness_id, harness, executor)
                    for harness_id, harness in providers
                )
            )
        finally:
            self._shutdown_discovery_executor(executor)
        summary_lines: list[str] = []
        discovery_failed = False
        for (_harness_id, harness), result in zip(
            providers,
            discoveries,
            strict=True,
        ):
            if result.error is not None:
                discovery_failed = True
                summary_lines.append(f"{harness.display_name} - failed: {result.error}")
                continue

            summary_lines.append(f"{harness.display_name} - {len(result.sessions)}")
        self._refresh_sidebar()
        self._refresh_status()

        if discovery_failed:
            completion_message = "Session discovery completed with errors:"
            severity = "warning"
        else:
            completion_message = "Session discovery was successful. Sessions found:"
            severity = "information"
        self.notify(
            "\n".join((completion_message, *summary_lines)),
            title="Session discovery",
            severity=severity,
            markup=False,
        )

    def _start_native_session_discovery(self) -> None:
        """Schedule one discovery cycle unless another is already running."""

        if not self._native_session_service.harness_ids or self._discovery_in_progress:
            return
        self._discovery_in_progress = True
        self.run_worker(
            self._discover_native_sessions(),
            group="native-session-discovery",
        )

    async def _discover_from_service(
        self,
        harness_id: str,
        executor: ThreadPoolExecutor,
    ) -> _DiscoveryResult:
        """Normalize one provider's discoveries while containing its failures."""

        future = None
        try:
            future = executor.submit(self._native_session_service.discover, harness_id)
            async with asyncio.timeout(10):
                while not future.done():
                    await asyncio.sleep(0.01)
                native_sessions = future.result()
        except Exception as error:  # noqa: BLE001 - providers fail independently
            detail = str(error) or type(error).__name__
            return _DiscoveryResult(error=detail)
        finally:
            if future is not None and not future.done():
                future.cancel()
        return _DiscoveryResult(sessions=native_sessions)

    async def _discover_and_reconcile_provider(
        self,
        harness_id: str,
        harness: AgentHarness,
        executor: ThreadPoolExecutor,
    ) -> _DiscoveryResult:
        """Discover and normally reconcile exactly one serialized provider."""

        async with self._provider_lock(harness.id):
            result = await self._discover_from_service(harness_id, executor)
            if result.error is not None:
                return result
            native_sessions = tuple(
                session
                for session in result.sessions
                if session.harness_id == harness.id
            )
            self.session_manager.reconcile_discovered(
                native_sessions=native_sessions,
                harness=harness,
            )
            return _DiscoveryResult(sessions=native_sessions)

    async def _reconcile_native_provider(self, harness_id: str) -> _DiscoveryResult:
        """Run normal reconciliation for one harness and no unrelated providers."""

        harness = self._agent_harnesses.get(harness_id)
        if harness is None:
            return _DiscoveryResult(error="native-session adapter is unavailable")

        executor = self._create_discovery_executor(max_workers=1)
        try:
            return await self._discover_and_reconcile_provider(harness_id, harness, executor)
        finally:
            self._shutdown_discovery_executor(executor)

    def _provider_lock(self, harness_id: str) -> asyncio.Lock:
        """Return the app-owned serialization lock for one native provider."""

        lock = self._provider_locks.get(harness_id)
        if lock is None:
            lock = asyncio.Lock()
            self._provider_locks[harness_id] = lock
        return lock

    def _create_discovery_executor(self, *, max_workers: int) -> ThreadPoolExecutor:
        """Create and track a bounded executor outside Python's default pool."""

        executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="agenthub-discovery",
        )
        self._discovery_executors.add(executor)
        self._discovery_executor = executor
        return executor

    def _shutdown_discovery_executor(
        self,
        executor: ThreadPoolExecutor | None = None,
    ) -> None:
        """Release queued discovery work without waiting on the Textual thread."""

        target = self._discovery_executor if executor is None else executor
        if target is None:
            return
        target.shutdown(wait=False, cancel_futures=True)
        self._discovery_executors.discard(target)
        if self._discovery_executor is target:
            self._discovery_executor = next(iter(self._discovery_executors), None)

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Gate hub-owned keys while an active terminal owns the keyboard."""

        # Textual contributes a hidden Ctrl+Q binding from its base App class.
        # Disable only binding dispatch; the palette calls action_quit directly.
        if action == "quit":
            return False

        terminal_is_active = self.session_manager.active_session is not None
        if self.hub_locked and terminal_is_active and action in TERMINAL_GATED_ACTIONS:
            return False
        return super().check_action(action, parameters)

    def watch_hub_locked(self, locked: bool) -> None:
        """Keep binding metadata and the authoritative status text current."""

        self.refresh_bindings()
        if not self.is_running:
            return
        status_bars = self.query(AgentHubStatusBar).nodes
        if status_bars:
            status_bars[0].update_mode(locked)

    def action_toggle_hub_lock(self) -> None:
        """Transfer navigation-key ownership between AgentHub and the terminal."""

        self.hub_locked = not self.hub_locked
        if not self.hub_locked:
            return

        current_screen = self.screen
        terminal_is_active = self.session_manager.active_session is not None
        if isinstance(current_screen, CommandPalette) or (
            terminal_is_active and isinstance(current_screen, ModalScreen)
        ):
            current_screen.dismiss()
        self.call_after_refresh(self._focus_active_terminal)

    def action_new_shell(self) -> None:
        """Begin the user-driven New Shell Session modal workflow."""

        if isinstance(self.screen, _SESSION_WORKFLOW_MODALS):
            return

        self.push_screen(ShellSessionNameInputModal(), self._on_shell_name_selected)

    async def _on_shell_name_selected(self, name: str | None) -> None:
        """Create and focus a new Fish shell session with the specified or default name."""

        if name is None:
            return

        session = await self._create_and_mount_session(
            name=name,
            harness=self._shell_harness,
            kind=SessionKind.SHELL,
            cwd=Path.cwd(),
        )
        self._refresh_sidebar()
        if session in self.session_manager.sessions:
            self.show_session(session.id)

    def get_system_commands(self, screen: Screen) -> Iterable[SystemCommand]:
        """Expose existing AgentHub actions through Textual's command palette."""

        for command in super().get_system_commands(screen):
            if command.title == "Keys":
                yield SystemCommand(
                    "Shortcuts",
                    command.help,
                    command.callback,
                    command.discover,
                )
            elif command.title == "Quit":
                yield SystemCommand(
                    "Quit AgentHub",
                    command.help,
                    command.callback,
                    command.discover,
                )
            else:
                yield command

        yield SystemCommand(
            "New Agent",
            "Create a new coding-agent session",
            self.action_new_session,
        )
        yield SystemCommand(
            "New Shell",
            "Create a new Fish shell session",
            self.action_new_shell,
        )
        yield SystemCommand(
            "Refresh Native Sessions",
            "Discover provider-native conversations again",
            self.action_resync_sessions,
        )
        yield SystemCommand(
            "Open Session",
            "Select and open an Agent or Shell session",
            self.action_open_session,
        )
        yield from self._contextual_system_commands()

    def action_command_palette(self) -> None:
        """Open the palette with an immutable snapshot of its session target."""

        if not self.use_command_palette or CommandPalette.is_open(self):
            return

        self._command_palette_target_id = self._resolve_palette_session_id()
        self.push_screen(
            CommandPalette(id="--command-palette"),
            self._on_command_palette_closed,
        )

    def _on_command_palette_closed(self, _result: object) -> None:
        """Discard context after the palette's ID-bound callbacks are built."""

        self._command_palette_target_id = None

    def _resolve_palette_session_id(self) -> str | None:
        """Resolve only the session displayed in the main terminal area."""

        if isinstance(self.screen, ModalScreen):
            return None

        active = self.session_manager.active_session
        if active is not None and active.terminal is not None:
            return active.id
        return None

    def _contextual_system_commands(self) -> Iterable[SystemCommand]:
        """Yield lifecycle commands bound to the palette's captured session ID."""

        session_id = self._command_palette_target_id
        if session_id is None:
            return
        try:
            session = self.session_manager.get(session_id)
        except KeyError:
            return

        if self._can_link_native_session(session):
            yield SystemCommand(
                f'Link "{session.name}"',
                "Link this running Agent to a native conversation",
                partial(self._begin_native_session_link, session.id),
            )
        if self._can_offer_native_session_delete(session):
            yield SystemCommand(
                f'Delete "{session.name}"',
                "Permanently delete this native conversation",
                partial(self._request_native_session_delete, session.id),
            )

    def _can_link_native_session(self, session: AgentSession) -> bool:
        """Return whether a running fresh Agent has a safe link candidate."""

        return (
            session.kind is SessionKind.AGENT
            and session.native_session_id is None
            and session.terminal is not None
            and session.state is SessionState.RUNNING
            and session.terminal.is_process_running
            and bool(self.session_manager.linkable_native_sessions(session.id))
        )

    def _can_offer_native_session_delete(self, session: AgentSession) -> bool:
        """Return whether Delete can act or provide provider-specific guidance."""

        return (
            session.kind is SessionKind.AGENT
            and session.native_session_id is not None
            and session.state in {SessionState.RUNNING, SessionState.UNLOADED}
            and self._native_session_service.delete_capability(session.harness.id) is not None
        )

    def action_new_session(self) -> None:
        """Begin the user-driven New Agent Session modal workflow."""

        if isinstance(self.screen, _SESSION_WORKFLOW_MODALS):
            return

        self.push_screen(
            HarnessPickerModal(self._agent_harnesses.values()),
            self._on_harness_selected,
        )

    def action_resync_sessions(self) -> None:
        """Refresh provider-native sessions without restarting live runtimes."""

        self._start_native_session_discovery()

    def action_open_session(self) -> None:
        """Open the unified picker for managed Agent and Shell sessions."""

        if isinstance(self.screen, _SESSION_WORKFLOW_MODALS):
            return

        sessions = self._openable_sessions()
        if not sessions:
            self.notify(
                "No sessions are available to open.",
                severity="information",
            )
            return

        self.push_screen(
            SessionPickerModal(sessions),
            self._on_open_session_selected,
        )

    def _openable_sessions(self) -> tuple[AgentSession, ...]:
        """Return sessions whose existing runtime or native identity can be opened."""

        return tuple(
            session
            for session in self.session_manager.sessions
            if (
                session.terminal is not None
                and session.state is SessionState.RUNNING
            )
            or (
                session.kind is SessionKind.AGENT
                and session.native_session_id is not None
                and session.state is SessionState.UNLOADED
            )
        )

    async def _on_open_session_selected(self, session_id: str | None) -> None:
        """Revalidate and activate the session selected by the picker."""

        if session_id is None:
            return

        try:
            session = self.session_manager.get(session_id)
        except KeyError:
            self.notify(
                "The selected session is no longer available.",
                severity="warning",
            )
            return

        if session not in self._openable_sessions():
            self.notify(
                "The selected session can no longer be opened.",
                severity="warning",
            )
            return

        await self.activate_session(session.id)

    def _begin_native_session_link(self, session_id: str) -> None:
        """Open native reconciliation for one explicit AgentHub session ID."""

        if isinstance(self.screen, _SESSION_WORKFLOW_MODALS):
            return
        try:
            pending = self.session_manager.get(session_id)
        except KeyError:
            self.notify(
                "The selected Agent session is no longer available.",
                severity="warning",
            )
            return
        if pending.kind is not SessionKind.AGENT:
            self.notify(
                "The selected session is not an Agent and cannot be linked.",
                severity="warning",
            )
            return
        if pending.native_session_id is not None:
            self.notify(
                f"{pending.name} is already linked to a native session.",
                severity="warning",
            )
            return
        if (
            pending.terminal is None
            or pending.state is not SessionState.RUNNING
            or not pending.terminal.is_process_running
        ):
            self.notify(
                "The selected fresh agent does not have a running terminal.",
                severity="warning",
            )
            return

        candidates = self.session_manager.linkable_native_sessions(pending.id)
        if not candidates:
            self.notify(
                "No unloaded native sessions from this harness and working "
                "directory are available. "
                "Run Ctrl+Shift+R after the native conversation exists.",
                severity="warning",
            )
            return

        self.push_screen(
            SessionLinkModal(pending.harness.display_name, candidates),
            partial(self._on_native_session_link_selected, pending.id),
        )

    def _request_native_session_delete(self, session_id: str) -> None:
        """Validate one explicit session ID and request native deletion."""

        if isinstance(self.screen, _SESSION_WORKFLOW_MODALS):
            return
        try:
            session = self.session_manager.get(session_id)
        except KeyError:
            self.notify(
                "The selected Agent session is no longer available.",
                severity="warning",
            )
            return
        if session.kind is not SessionKind.AGENT:
            self.notify(
                "The selected session is not an Agent and cannot be deleted.",
                severity="warning",
            )
            return
        if session.native_session_id is None:
            self.notify(
                "Fresh Agents are not linked to a native conversation and "
                "cannot be permanently deleted.",
                severity="warning",
            )
            return
        if session.state is SessionState.DELETING:
            self.notify(
                f"{session.name} is already being deleted.",
                severity="warning",
                markup=False,
            )
            return
        deletion_capability = self._native_session_service.delete_capability(session.harness.id)
        if deletion_capability is None:
            self.notify(
                f"No native-session adapter is available for {session.harness.display_name}.",
                severity="error",
            )
            return
        if not deletion_capability:
            self._notify_native_deletion_error(
                session,
                NativeSessionDeletionUnavailableError.for_provider(
                    session.harness.display_name
                ),
            )
            return
        if session.state not in {SessionState.RUNNING, SessionState.UNLOADED}:
            self.notify(
                "The selected Agent session can no longer be deleted.",
                severity="warning",
            )
            return

        self.push_screen(
            SessionDeleteConfirmationModal(session.name),
            partial(self._on_native_session_delete_confirmed, session.id),
        )

    async def _on_native_session_delete_confirmed(
        self,
        session_id: str,
        confirmed: bool,
    ) -> None:
        """Begin irreversible work only after an explicit modal confirmation."""

        if not confirmed:
            return
        await self._delete_native_session(session_id)

    def _notify_native_deletion_error(
        self,
        session: AgentSession,
        error: Exception,
    ) -> None:
        """Show provider-neutral failure or unsupported-provider guidance."""

        deletion_unavailable = isinstance(
            error,
            NativeSessionDeletionUnavailableError,
        )
        detail = str(error) or type(error).__name__
        self.notify(
            detail if deletion_unavailable else f"Could not delete {session.name}: {detail}",
            title=(
                "Native deletion unavailable"
                if deletion_unavailable
                else "Native session deletion failed"
            ),
            severity="warning" if deletion_unavailable else "error",
            markup=False,
        )

    async def _delete_native_session(self, session_id: str) -> None:
        """Stop a runtime, delete natively, verify absence, then remove its row."""

        try:
            session = self.session_manager.get(session_id)
        except KeyError:
            self.notify(
                "The selected Agent session is no longer available.",
                severity="error",
            )
            return

        if session.kind is not SessionKind.AGENT or session.native_session_id is None:
            self.notify(
                "The selected Agent is not eligible for native deletion.",
                severity="error",
            )
            return
        deletion_capability = self._native_session_service.delete_capability(session.harness.id)
        if deletion_capability is None:
            self.notify(
                "The selected Agent is not eligible for native deletion.",
                severity="error",
            )
            return
        if not deletion_capability:
            self._notify_native_deletion_error(
                session,
                NativeSessionDeletionUnavailableError.for_provider(
                    session.harness.display_name
                ),
            )
            return

        native_session = NativeSession(
            harness_id=session.harness.id,
            native_session_id=session.native_session_id,
            name=session.name,
            cwd=session.cwd,
        )
        harness = session.harness
        was_active = self.session_manager.active_session is session
        try:
            terminal = self.session_manager.begin_native_deletion(session.id)
        except ValueError as error:
            self.notify(f"Could not delete {session.name}: {error}", severity="error")
            return
        self._revoke_activity_tracking(session.id)

        if was_active:
            self._show_home()
        self._refresh_sidebar()
        self._refresh_status()

        try:
            if terminal is not None and terminal.is_mounted:
                await terminal.remove()
            if terminal is not None and terminal.is_process_running:
                raise NativeSessionDeletionError(
                    "the native runtime could not be stopped safely"
                )

            executor = self._create_discovery_executor(max_workers=1)
            try:
                async with self._provider_lock(harness.id):
                    await self._native_session_service.delete(native_session)
                    discovery = await self._discover_from_service(harness.id, executor)
                    if discovery.error is not None:
                        raise NativeSessionDeletionError(
                            f"could not verify deletion: {discovery.error}"
                        )
                    native_sessions = tuple(
                        discovered
                        for discovered in discovery.sessions
                        if discovered.harness_id == harness.id
                    )
                    if any(
                        discovered.native_session_id
                        == native_session.native_session_id
                        for discovered in native_sessions
                    ):
                        raise NativeSessionDeletionError(
                            "the provider still reports the conversation"
                        )

                    self.session_manager.complete_native_deletion(session.id)
                    self.session_manager.reconcile_discovered(
                        native_sessions=native_sessions,
                        harness=harness,
                    )
            finally:
                self._shutdown_discovery_executor(executor)
        except Exception as error:  # noqa: BLE001 - preserve row across provider boundary
            try:
                current = self.session_manager.get(session.id)
            except KeyError:
                current = None
            if current is not None and current.state is SessionState.DELETING:
                self.session_manager.fail_native_deletion(session.id)
            self._refresh_sidebar()
            self._refresh_status()
            self._notify_native_deletion_error(session, error)
            return

        self._refresh_sidebar()
        self._refresh_status()
        self.notify(
            f'Deleted "{native_session.name}" permanently.',
            title="Native session deleted",
            markup=False,
        )

    def _on_native_session_link_selected(
        self,
        pending_session_id: str,
        native_session_row_id: str | None,
    ) -> None:
        """Apply a user-selected native identity after revalidating both rows."""

        if native_session_row_id is None:
            return

        try:
            pending = self.session_manager.get(pending_session_id)
            if pending.terminal is None or not pending.terminal.is_process_running:
                raise ValueError("the fresh agent terminal is no longer running")
            linked = self.session_manager.link_native_session(
                pending_session_id,
                native_session_row_id,
            )
        except (KeyError, ValueError) as error:
            self.notify(f"Could not link native session: {error}", severity="error")
            return

        self._refresh_sidebar()
        self._refresh_status()
        self.notify(
            f"Linked running terminal to {linked.name}.",
            title="Native session linked",
            markup=False,
        )

    def _on_harness_selected(self, harness_id: str | None) -> None:
        """Continue the workflow by prompting for the working directory."""

        if harness_id is None:
            return

        harness = self._agent_harnesses[harness_id]
        self.push_screen(
            WorkingDirectoryPickerModal(root=self._working_directory_root),
            partial(self._on_working_directory_selected, harness),
        )

    async def _on_working_directory_selected(
        self,
        harness: AgentHarness,
        cwd: Path | None,
    ) -> None:
        """Create the runtime only after both modal stages are confirmed."""

        if cwd is None:
            return

        await self._create_agent_session(
            harness=harness,
            cwd=cwd,
        )

    async def _create_agent_session(
        self,
        *,
        harness: AgentHarness,
        cwd: Path,
    ) -> AgentSession:
        """Apply Agent-session policy around generic runtime creation."""

        session = await self._create_and_mount_session(
            name=_FRESH_AGENT_NAME,
            harness=harness,
            kind=SessionKind.AGENT,
            cwd=cwd,
        )
        self._refresh_sidebar()
        if session in self.session_manager.sessions:
            self.show_session(session.id)
        return session

    def action_focus_sidebar(self) -> None:
        """Move keyboard focus to the selected sidebar category."""

        self.query_one(SessionSidebar).focus_sidebar()

    async def _create_and_mount_session(
        self,
        *,
        name: str,
        harness: AgentHarness,
        kind: SessionKind,
        cwd: Path,
    ) -> AgentSession:
        """Create one manager-owned session and mount its terminal in the shell."""

        previous_session = self.session_manager.active_session
        session = self.session_manager.create(
            name=name,
            kind=kind,
            cwd=cwd,
            harness=harness,
        )
        if session.terminal is None:
            raise RuntimeError("new runtime session did not create a terminal")
        session.terminal.id = self._terminal_dom_id(session.id)
        try:
            activity_tracking_ready = await self._prepare_activity_tracking(
                session,
                session.terminal,
            )
            await self.query_one("#session-content", ContentSwitcher).mount(session.terminal)
            if activity_tracking_ready:
                self._initialize_mounted_activity(session)
        except Exception:
            self._revoke_activity_tracking(session.id)
            if session in self.session_manager.sessions:
                self.session_manager.remove(session.id)
                if previous_session in self.session_manager.sessions:
                    self.session_manager.select(previous_session.id)
            raise
        self.call_after_refresh(self._refresh_status)
        return session

    async def _prepare_activity_tracking(
        self,
        session: AgentSession,
        terminal: AgentTerminal,
    ) -> bool:
        """Best-effort configure provider observation before its child starts."""

        if session.kind is not SessionKind.AGENT:
            return False
        try:
            launch = await self._activity_service.prepare(
                session.id,
                session.harness.id,
                terminal.child_command,
                native_session_id=session.native_session_id,
            )
            if launch is None:
                return False
            terminal.configure_launch(
                command=launch.command,
                environment_overrides=dict(launch.environment_overrides),
            )
            terminal.set_forwarded_key_observer(partial(self._on_activity_terminal_key, session.id))
            return True
        except Exception:  # noqa: BLE001 - activity must never prevent a launch
            self._revoke_activity_tracking(session.id)
            return False

    def _initialize_mounted_activity(self, session: AgentSession) -> None:
        """Initialize providers that do not report their own observer readiness."""

        if session.activity is not AgentActivity.UNKNOWN:
            return
        event = self._activity_service.initial_event(session.id)
        if event is not None:
            self._apply_activity_event(event)

    def _revoke_activity_tracking(self, session_id: str) -> None:
        """Invalidate one runtime's activity credential if it exists."""

        try:
            terminal = self.session_manager.get(session_id).terminal
        except KeyError:
            terminal = None
        if terminal is not None:
            terminal.set_forwarded_key_observer(None)
        self._activity_service.revoke(session_id)

    def _on_activity_event(self, event: AgentActivityEvent) -> None:
        """Apply one authenticated event and refresh only presentation state."""

        self._apply_activity_event(event)

    def _apply_activity_event(self, event: AgentActivityEvent) -> bool:
        """Apply one event, then evaluate its actual visible transition."""

        try:
            session = self.session_manager.get(event.session_id)
        except KeyError:
            return False
        previous_activity = session.activity
        if not self.session_manager.apply_activity_event(event):
            return False

        self._refresh_sidebar()
        self._notification_service.handle_activity_transition(
            previous_activity,
            session.activity,
            harness_name=session.harness.display_name,
            session_title=session.name,
            is_loaded_agent=(
                session.kind is SessionKind.AGENT
                and session.terminal is not None
                and session.state is SessionState.RUNNING
            ),
        )
        return True

    def _on_activity_terminal_key(self, session_id: str, key: str) -> None:
        """Route forwarded terminal keys through the provider-neutral service."""
        try:
            session = self.session_manager.get(session_id)
        except KeyError:
            return
        event = self._activity_service.terminal_key_event(
            session_id,
            key,
            activity=session.activity,
            input_wait_kind=self.session_manager.input_wait_kind(session_id),
        )
        if event is not None:
            self._apply_activity_event(event)

    def _agent_sessions(self) -> tuple[AgentSession, ...]:
        """Return managed coding-agent sessions in creation order."""

        return tuple(
            session
            for session in self.session_manager.sessions
            if session.kind is SessionKind.AGENT
        )

    def _shell_sessions(self) -> tuple[AgentSession, ...]:
        """Return managed shell sessions in creation order."""

        return tuple(
            session
            for session in self.session_manager.sessions
            if session.kind is SessionKind.SHELL
        )

    def _refresh_sidebar(self) -> None:
        """Synchronize grouped session presentation with application state."""

        sidebars = self.query(SessionSidebar).nodes
        if not sidebars:
            return
        sidebars[0].update_sessions(self.session_manager.sessions)

    def _highlight_active_sidebar(self) -> None:
        """Restore active highlighting after a sidebar recompose."""

        session = self.session_manager.active_session
        sidebars = self.query(SessionSidebar).nodes
        if session is not None and sidebars:
            sidebars[0].set_active(session.id)

    def _focus_active_terminal(self) -> None:
        """Restore active-row context and focus after entering terminal-first mode."""

        session = self.session_manager.active_session
        if session is not None and session.terminal is not None:
            self.query_one(SessionSidebar).set_active(session.id)
            self.set_focus(session.terminal)

    async def on_session_sidebar_session_selected(
        self,
        message: SessionSidebar.SessionSelected,
    ) -> None:
        """Route sidebar navigation through the shared switching operation."""

        await self.activate_session(message.session_id)

    async def on_agent_terminal_process_exited(
        self,
        message: AgentTerminal.ProcessExited,
    ) -> None:
        """Resolve terminal exit events to their owning AgentHub session."""

        session = self.session_manager.find_by_terminal(message.control)
        if session is not None:
            await self._handle_session_process_exited(session, message.exit_code)

    def _refresh_status(self) -> None:
        """Update the status bar using only current runtime facts."""

        sessions = self.session_manager.sessions
        running_agents = sum(
            session.terminal is not None and session.terminal.is_process_running
            for session in self._agent_sessions()
        )
        self.query_one(AgentHubStatusBar).update_state(
            session_count=len(sessions),
            running_count=running_agents,
            locked=self.hub_locked,
        )

    async def _handle_session_process_exited(
        self,
        session: AgentSession,
        _exit_code: int,
    ) -> None:
        """Retain resumable native Agents and remove disposable runtimes."""

        if session.kind is SessionKind.AGENT and session.native_session_id is not None:
            await self._unload_exited_native_session(session)
        else:
            await self._remove_exited_session(session)

    async def _unload_exited_native_session(self, session: AgentSession) -> None:
        """Detach an exited runtime and reconcile only its native provider."""

        if session not in self.session_manager.sessions:
            return

        was_active = self.session_manager.active_session is session
        self._revoke_activity_tracking(session.id)
        terminal = self.session_manager.detach_terminal(session.id)
        if was_active:
            self.session_manager.clear_selection()
            self._show_home()

        if terminal is not None and terminal.is_mounted:
            await terminal.remove()

        self._refresh_sidebar()
        self._refresh_status()
        result = await self._reconcile_native_provider(session.harness.id)
        self._refresh_sidebar()
        self._refresh_status()
        if result.error is not None:
            self.notify(
                f"Could not reconcile {session.harness.display_name} after exit: "
                f"{result.error}",
                title="Session reconciliation failed",
                severity="warning",
                markup=False,
            )

    async def _remove_exited_session(self, session: AgentSession) -> None:
        """Synchronize process-exit cleanup across manager, DOM, and UI."""

        if session not in self.session_manager.sessions:
            return

        was_active = self.session_manager.active_session is session
        terminal = session.terminal
        self._revoke_activity_tracking(session.id)
        self.session_manager.remove(session.id)
        if was_active:
            self._show_home()

        if terminal is not None and terminal.is_mounted:
            await terminal.remove()

        self._refresh_sidebar()
        self._refresh_status()

    def _show_home(self) -> None:
        """Display and focus Home without changing keyboard-ownership mode."""

        home = self.query_one(HomeScreen)
        self.query_one("#session-content", ContentSwitcher).current = "home-screen"
        sidebar = self.query_one(SessionSidebar)
        sidebar.clear_active()
        sidebar.clear_navigation()
        self.set_focus(home)
