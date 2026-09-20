"""Shared passive hook forwarding for command-based provider integrations."""

from __future__ import annotations

import json
import os
import socket
import sys
from collections.abc import Mapping
from typing import BinaryIO, TextIO
from urllib.parse import urlsplit

AGENTHUB_SESSION_ID = "AGENTHUB_SESSION_ID"
AGENTHUB_ACTIVITY_ENDPOINT = "AGENTHUB_ACTIVITY_ENDPOINT"
AGENTHUB_ACTIVITY_TOKEN = "AGENTHUB_ACTIVITY_TOKEN"

_MAX_INPUT_BYTES = 1_000_000
_NEUTRAL_RESPONSE = "{}\n"
_PROTOCOL_VERSION = 1


def _write_neutral_response(output: TextIO, response: Mapping[str, object]) -> None:
    try:
        if response:
            output.write(json.dumps(response, separators=(",", ":")) + "\n")
        else:
            output.write(_NEUTRAL_RESPONSE)
        output.flush()
    except Exception:  # noqa: BLE001, S110 - observation must never affect providers
        pass


def _loopback_address(endpoint: str) -> tuple[str, int] | None:
    """Parse only the loopback TCP endpoint format emitted by AgentHub."""

    try:
        parsed = urlsplit(endpoint)
        if (
            parsed.scheme != "tcp"
            or parsed.hostname != "127.0.0.1"
            or parsed.port is None
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            return None
        return parsed.hostname, parsed.port
    except ValueError:
        return None


def run_activity_hook(
    provider: str,
    *,
    input_stream: BinaryIO | None = None,
    output_stream: TextIO | None = None,
    environment: Mapping[str, str] | None = None,
    payload_updates: Mapping[str, object] | None = None,
    neutral_response: Mapping[str, object] | None = None,
) -> int:
    """Forward one provider event locally and always return a neutral result."""

    source = sys.stdin.buffer if input_stream is None else input_stream
    output = sys.stdout if output_stream is None else output_stream
    env = os.environ if environment is None else environment
    try:
        payload = source.read(_MAX_INPUT_BYTES + 1)
        if len(payload) > _MAX_INPUT_BYTES:
            raise ValueError("hook payload exceeded the local receiver limit")
        decoded = json.loads(payload)
        if not isinstance(decoded, dict):
            raise TypeError("hook payload was not an object")
        if payload_updates:
            decoded.update(payload_updates)

        session_id = env.get(AGENTHUB_SESSION_ID, "")
        endpoint = _loopback_address(env.get(AGENTHUB_ACTIVITY_ENDPOINT, ""))
        token = env.get(AGENTHUB_ACTIVITY_TOKEN, "")
        if not session_id or endpoint is None or not token:
            raise ValueError("activity forwarding is not configured")

        envelope = json.dumps(
            {
                "version": _PROTOCOL_VERSION,
                "provider": provider,
                "session_id": session_id,
                "token": token,
                "event": decoded,
            },
            separators=(",", ":"),
        ).encode("utf-8") + b"\n"
        with socket.create_connection(endpoint, timeout=0.25) as connection:
            connection.settimeout(0.25)
            connection.sendall(envelope)
    except Exception:  # noqa: BLE001, S110 - activity is strictly best effort
        pass

    _write_neutral_response(output, neutral_response or {})
    return 0


__all__ = [
    "AGENTHUB_ACTIVITY_ENDPOINT",
    "AGENTHUB_ACTIVITY_TOKEN",
    "AGENTHUB_SESSION_ID",
    "run_activity_hook",
]
