"""Provider-neutral native conversation models."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class NativeSession:
    """One conversation discovered from a native coding-agent harness."""

    harness_id: str
    native_session_id: str
    name: str
    cwd: Path | None = None


@dataclass(frozen=True)
class LaunchSpec:
    """Exact command and child working directory for a native conversation."""

    command: tuple[str, ...]
    working_directory: Path
