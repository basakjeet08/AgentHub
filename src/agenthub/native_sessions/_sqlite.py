"""Read-only SQLite helpers for provider-owned metadata stores."""

import sqlite3
from collections.abc import Callable, Sequence
from pathlib import Path


def read_rows[T](
    database: Path,
    query: str,
    convert: Callable[[sqlite3.Row], T],
) -> tuple[T, ...]:
    """Read and convert rows without creating or modifying a provider database."""

    uri = f"{database.resolve().as_uri()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=1)
    connection.row_factory = sqlite3.Row
    try:
        rows: Sequence[sqlite3.Row] = connection.execute(query).fetchall()
        return tuple(convert(row) for row in rows)
    finally:
        connection.close()
