"""Logical model for one AgentHub-managed session."""

from dataclasses import dataclass
from pathlib import Path

from agenthub_v2.activity import Activity


@dataclass
class Session:
    """In-memory identity and state of an AgentHub session."""

    id: str
    name: str
    cwd: Path

    is_loaded: bool = False
    is_shell: bool = False

    provider_id: str | None = None
    provider_session_id: str | None = None
    activity: Activity = Activity.UNKNOWN
