"""Collection and active-session coordination for AgentHub runtimes."""

from pathlib import Path
from uuid import uuid4

from agenthub.harnesses import AgentHarness
from agenthub.terminal import AgentTerminal

from .model import AgentSession


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

    def create(
        self,
        *,
        name: str,
        cwd: Path,
        harness: AgentHarness,
    ) -> AgentSession:
        """Create a session and make it active without mounting its terminal."""

        working_directory = cwd.expanduser().resolve()
        session = AgentSession(
            id=uuid4().hex,
            name=name,
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

    def select(self, session_id: str) -> AgentSession:
        """Select and return an existing session.

        Raises:
            KeyError: If ``session_id`` is not managed by this instance.
        """

        session = self._sessions[session_id]
        self._active_session_id = session_id
        return session
