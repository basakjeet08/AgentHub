"""Authenticated loopback receiver for provider activity observations."""

from __future__ import annotations

import asyncio
import hmac
import json
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from ._forwarder import (
    AGENTHUB_ACTIVITY_ENDPOINT,
    AGENTHUB_ACTIVITY_TOKEN,
    AGENTHUB_SESSION_ID,
)
from .antigravity import AntigravityActivityNormalizer
from .codex import normalize_codex_activity
from .devin import normalize_devin_activity
from .model import AgentActivityEvent
from .opencode import normalize_opencode_activity

_HOST = "127.0.0.1"
_MAX_MESSAGE_BYTES = 1_048_576
_PROTOCOL_VERSION = 1
_NORMALIZERS = {
    "codex": normalize_codex_activity,
    "devin": normalize_devin_activity,
    "opencode": normalize_opencode_activity,
}


@dataclass(frozen=True)
class ActivityRegistration:
    """One exact logical-session route and its child-only environment."""

    session_id: str
    provider: str
    token: str
    endpoint: str

    @property
    def environment(self) -> Mapping[str, str]:
        """Return the values injected only into this provider process."""

        return {
            AGENTHUB_SESSION_ID: self.session_id,
            AGENTHUB_ACTIVITY_ENDPOINT: self.endpoint,
            AGENTHUB_ACTIVITY_TOKEN: self.token,
        }


class ActivityReceiver:
    """Accept small authenticated event envelopes on an ephemeral loopback port."""

    def __init__(self, on_event: Callable[[AgentActivityEvent], None]) -> None:
        self._on_event = on_event
        self._server: asyncio.Server | None = None
        self._registrations: dict[str, ActivityRegistration] = {}
        self._normalizers: dict[
            str,
            Callable[[str, object], AgentActivityEvent | None],
        ] = {}

    @property
    def endpoint(self) -> str:
        """Return the bound endpoint after startup."""

        server = self._server
        if server is None or not server.sockets:
            raise RuntimeError("activity receiver is not running")
        port = server.sockets[0].getsockname()[1]
        return f"tcp://{_HOST}:{port}"

    async def start(self) -> None:
        """Bind once to an OS-selected loopback port."""

        if self._server is None:
            self._server = await asyncio.start_server(
                self._handle_connection,
                host=_HOST,
                port=0,
                limit=_MAX_MESSAGE_BYTES + 1,
            )

    def register(
        self,
        session_id: str,
        provider: str,
        *,
        native_session_id: str | None = None,
    ) -> ActivityRegistration:
        """Create an unguessable route for exactly one logical session."""

        if self._server is None:
            raise RuntimeError("activity receiver is not running")
        token = secrets.token_urlsafe(32)
        registration = ActivityRegistration(
            session_id=session_id,
            provider=provider,
            token=token,
            endpoint=self.endpoint,
        )
        self._registrations[token] = registration
        if provider == "antigravity":
            self._normalizers[token] = AntigravityActivityNormalizer(
                native_session_id
            )
        else:
            normalizer = _NORMALIZERS.get(provider)
            if normalizer is not None:
                self._normalizers[token] = normalizer
        return registration

    def revoke(self, registration: ActivityRegistration) -> None:
        """Remove a route only if the exact registration still owns it."""

        current = self._registrations.get(registration.token)
        if current == registration:
            self._registrations.pop(registration.token, None)
            self._normalizers.pop(registration.token, None)

    async def close(self) -> None:
        """Stop listening and discard every session credential."""

        server = self._server
        self._server = None
        self._registrations.clear()
        self._normalizers.clear()
        if server is not None:
            server.close()
            await server.wait_closed()

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Validate and normalize one newline-delimited event envelope."""

        try:
            raw = await asyncio.wait_for(reader.readline(), timeout=1)
            if not raw or len(raw) > _MAX_MESSAGE_BYTES or not raw.endswith(b"\n"):
                return
            envelope = json.loads(raw)
            event = self._resolve_event(envelope)
            if event is not None:
                self._on_event(event)
        except (TimeoutError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            return
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass

    def _resolve_event(self, envelope: object) -> AgentActivityEvent | None:
        """Authenticate an envelope before exposing its normalized event."""

        if not isinstance(envelope, dict) or envelope.get("version") != _PROTOCOL_VERSION:
            return None
        token = envelope.get("token")
        if not isinstance(token, str):
            return None
        registration = self._registrations.get(token)
        if registration is None or not hmac.compare_digest(registration.token, token):
            return None
        if (
            envelope.get("session_id") != registration.session_id
            or envelope.get("provider") != registration.provider
        ):
            return None
        normalizer = self._normalizers.get(token)
        if normalizer is None:
            return None
        return normalizer(registration.session_id, envelope.get("event"))


__all__ = ["ActivityReceiver", "ActivityRegistration"]
