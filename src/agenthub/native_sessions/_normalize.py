"""Shared validation for provider-owned session metadata."""

from collections.abc import Iterable
from pathlib import Path

from .model import NativeSession


def normalize_session(
    harness_id: str,
    native_session_id: object,
    name: object,
    cwd: Path | None,
) -> NativeSession | None:
    """Normalize one provider record, rejecting records without an identity."""

    normalized_id = str(native_session_id or "").strip()
    if not normalized_id:
        return None
    normalized_name = str(name or "").strip() or "Untitled"
    return NativeSession(harness_id, normalized_id, normalized_name, cwd)


def unique_sessions(
    sessions: Iterable[NativeSession | None],
) -> tuple[NativeSession, ...]:
    """Discard invalid records and preserve the first occurrence of each native ID."""

    unique: list[NativeSession] = []
    seen_ids: set[str] = set()
    for session in sessions:
        if session is None or session.native_session_id in seen_ids:
            continue
        seen_ids.add(session.native_session_id)
        unique.append(session)
    return tuple(unique)
