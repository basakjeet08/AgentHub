"""Provider-neutral contracts for activity integrations."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol, TextIO

from .model import AgentActivity, AgentActivityEvent, AgentActivityEventKind

ActivityNormalizer = Callable[[str, object], AgentActivityEvent | None]


@dataclass(frozen=True)
class ActivityLaunch:
    """Provider-prepared launch data consumed by the terminal boundary."""

    command: tuple[str, ...]
    environment_overrides: Mapping[str, str]
    artifacts: tuple[Path, ...] = ()
    reports_session_started: bool = False


class ActivityAdapter(Protocol):
    """Provider-specific activity behavior required by AgentHub."""

    harness_id: str

    def matches_command(self, command: Sequence[str]) -> bool:
        """Return whether this adapter can instrument ``command``."""

    def create_normalizer(self, native_session_id: str | None) -> ActivityNormalizer:
        """Create the per-runtime normalizer used by the receiver."""

    def prepare_launch(
        self,
        command: Sequence[str],
        *,
        native_session_id: str | None,
        registration_environment: Mapping[str, str],
    ) -> ActivityLaunch:
        """Install/configure observation and prepare the child launch."""

    def run_hook(
        self,
        event_name: str | None = None,
        *,
        input_stream: BinaryIO | None = None,
        output_stream: TextIO | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> int:
        """Run the provider's passive hook helper."""

    def terminal_key_event(
        self,
        session_id: str,
        key: str,
        *,
        activity: AgentActivity,
        input_wait_kind: AgentActivityEventKind | None,
    ) -> AgentActivityEvent | None:
        """Translate provider-specific terminal keys into activity events."""
