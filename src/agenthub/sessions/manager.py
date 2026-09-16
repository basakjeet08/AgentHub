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
