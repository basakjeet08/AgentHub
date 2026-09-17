"""Collection and active-session coordination for AgentHub runtimes."""

from pathlib import Path
from uuid import uuid4

from agenthub.harnesses import AgentHarness
from agenthub.native_sessions import NativeSession
from agenthub.terminal import AgentTerminal

from .model import AgentSession, SessionKind, SessionState


class SessionManager:
    """Create, retain, enumerate, and select AgentHub sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, AgentSession] = {}
        self._active_session_id: str | None = None

    @property
    def sessions(self) -> tuple[AgentSession, ...]:
        """Return sessions in creation order."""

        return tuple(self._sessions.values())

    @property
    def active_session(self) -> AgentSession | None:
        """Return the selected session, or ``None`` when none exist."""

        if self._active_session_id is None:
            return None
        return self._sessions[self._active_session_id]

    def get(self, session_id: str) -> AgentSession:
        """Return one managed session by its ephemeral AgentHub identity."""

        return self._sessions[session_id]

    def create(
        self,
        *,
        name: str,
        kind: SessionKind,
        cwd: Path,
        harness: AgentHarness,
    ) -> AgentSession:
        """Create a session and make it active without mounting its terminal."""

        working_directory = cwd.expanduser().resolve()
        session = AgentSession(
            id=uuid4().hex,
            name=name,
            kind=kind,
            cwd=working_directory,
            harness=harness,
            terminal=AgentTerminal(
                harness,
                working_directory=working_directory,
            ),
        )
        self._sessions[session.id] = session
        self._active_session_id = session.id
        return session

    def add_discovered(
        self,
        *,
        native_session: NativeSession,
        harness: AgentHarness,
    ) -> AgentSession:
        """Add one unloaded native conversation unless it is already managed."""

        if native_session.harness_id != harness.id:
            raise ValueError("native session and harness IDs do not match")
        existing = self.find_by_native_identity(
            native_session.harness_id,
            native_session.native_session_id,
        )
        if existing is not None:
            existing.name = native_session.name
            existing.cwd = native_session.cwd
            return existing

        session = AgentSession(
            id=uuid4().hex,
            name=native_session.name,
            kind=SessionKind.AGENT,
            cwd=native_session.cwd,
            harness=harness,
            terminal=None,
            native_session_id=native_session.native_session_id,
            state=SessionState.UNLOADED,
        )
        self._sessions[session.id] = session
        return session

    def reconcile_discovered(
        self,
        *,
        native_sessions: tuple[NativeSession, ...],
        harness: AgentHarness,
    ) -> tuple[AgentSession, ...]:
        """Synchronize one provider while preserving every live runtime."""

        native_ids = {
            native_session.native_session_id for native_session in native_sessions
        }
        stale_session_ids = tuple(
            session.id
            for session in self._sessions.values()
            if session.harness.id == harness.id
            and session.native_session_id is not None
            and session.native_session_id not in native_ids
            and session.terminal is None
            and session.state is SessionState.UNLOADED
        )
        for session_id in stale_session_ids:
            self.remove(session_id)

        return tuple(
            self.add_discovered(native_session=native_session, harness=harness)
            for native_session in native_sessions
        )

    def find_by_native_identity(
        self,
        harness_id: str,
        native_session_id: str,
    ) -> AgentSession | None:
        """Find a session by its provider-owned stable identity."""

        return next(
            (
                session
                for session in self._sessions.values()
                if session.harness.id == harness_id
                and session.native_session_id == native_session_id
            ),
            None,
        )

    def find_by_terminal(self, terminal: AgentTerminal) -> AgentSession | None:
        """Find the logical session currently owning ``terminal``."""

        return next(
            (
                session
                for session in self._sessions.values()
                if session.terminal is terminal
            ),
            None,
        )

    def linkable_native_sessions(
        self,
        pending_session_id: str,
    ) -> tuple[AgentSession, ...]:
        """Return safe manual-link targets for one pending running Agent."""

        pending = self._sessions[pending_session_id]
        if not self._is_linkable_pending_session(pending):
            return ()

        native_identity_counts: dict[tuple[str, str], int] = {}
        for session in self._sessions.values():
            if session.native_session_id is None:
                continue
            identity = (session.harness.id, session.native_session_id)
            native_identity_counts[identity] = native_identity_counts.get(identity, 0) + 1

        return tuple(
            session
            for session in self._sessions.values()
            if session.id != pending.id
            and session.id != self._active_session_id
            and session.kind is SessionKind.AGENT
            and session.harness.id == pending.harness.id
            and self._same_working_directory(session.cwd, pending.cwd)
            and session.native_session_id is not None
            and session.terminal is None
            and session.state is SessionState.UNLOADED
            and native_identity_counts[
                (session.harness.id, session.native_session_id)
            ]
            == 1
        )

    def link_native_session(
        self,
        pending_session_id: str,
        native_session_row_id: str,
    ) -> AgentSession:
        """Merge an unloaded native row into its user-selected running runtime.

        Every invariant is validated before either session is mutated. The
        pending row keeps its AgentHub identity, cwd, and terminal;
        provider-owned identity and title move onto it, and the duplicate
        unloaded row is removed.
        """

        pending = self._sessions[pending_session_id]
        candidate = self._sessions[native_session_row_id]
        if not self._is_linkable_pending_session(pending):
            raise ValueError("pending session is not a running unidentified Agent")
        if candidate not in self.linkable_native_sessions(pending.id):
            raise ValueError("native session is not a safe link target")

        pending.native_session_id = candidate.native_session_id
        pending.name = candidate.name
        self.remove(candidate.id)
        return pending

    @staticmethod
    def _is_linkable_pending_session(session: AgentSession) -> bool:
        """Return whether ``session`` can receive a native identity manually."""

        return (
            session.kind is SessionKind.AGENT
            and session.native_session_id is None
            and session.terminal is not None
            and session.state is SessionState.RUNNING
        )

    @staticmethod
    def _same_working_directory(first: Path | None, second: Path | None) -> bool:
        """Compare directory metadata after non-strict path normalization."""

        if first is None or second is None:
            return False
        try:
            return first.expanduser().resolve() == second.expanduser().resolve()
        except (OSError, RuntimeError):
            return False

    def attach_terminal(
        self,
        session_id: str,
        terminal: AgentTerminal,
    ) -> AgentSession:
        """Attach a newly constructed runtime to an unloaded session."""

        session = self._sessions[session_id]
        if session.terminal is not None:
            raise ValueError(f"session {session_id!r} already has a terminal")
        session.terminal = terminal
        session.state = SessionState.RUNNING
        return session

    def detach_terminal(self, session_id: str) -> AgentTerminal | None:
        """Detach and return a session's disposable runtime."""

        session = self._sessions[session_id]
        terminal = session.terminal
        session.terminal = None
        session.state = SessionState.UNLOADED
        return terminal

    def select(self, session_id: str) -> AgentSession:
        """Select and return an existing session.

        Raises:
            KeyError: If ``session_id`` is not managed by this instance.
        """

        session = self._sessions[session_id]
        self._active_session_id = session_id
        return session

    def clear_selection(self) -> None:
        """Clear the active logical session without removing it."""

        self._active_session_id = None

    def remove(self, session_id: str) -> AgentSession:
        """Remove and return a session without selecting a replacement.

        Removing an inactive session preserves the current selection. Removing
        the active session clears selection so the app can display Home.

        Raises:
            KeyError: If ``session_id`` is not managed by this instance.
        """

        session = self._sessions.pop(session_id)
        if self._active_session_id == session_id:
            self._active_session_id = None
        return session
