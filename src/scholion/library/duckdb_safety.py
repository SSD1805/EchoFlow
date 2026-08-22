"""Shared transaction safety for Scholion's rebuildable DuckDB projections.

This module centralizes atomic mutation semantics. It does not claim that a DuckDB file
is immune to disk, filesystem, or hardware corruption; Scholion deliberately keeps these
databases rebuildable from authoritative transcript and research state.
"""

from collections.abc import Iterator
from contextlib import contextmanager

import duckdb


@contextmanager
def atomic_duckdb_transaction(
    connection: duckdb.DuckDBPyConnection,
) -> Iterator[duckdb.DuckDBPyConnection]:
    """Commit a DuckDB mutation atomically or roll the whole transaction back.

    BaseException is intentionally covered so interrupts cannot strand a partially applied
    application-level mutation. If rollback itself fails, preserve the original exception
    and annotate it with the rollback failure instead of replacing the root cause.
    """

    connection.execute("BEGIN TRANSACTION")
    try:
        yield connection
        connection.execute("COMMIT")
    except BaseException as exc:
        try:
            connection.execute("ROLLBACK")
        except duckdb.Error as rollback_exc:
            exc.add_note(f"DuckDB rollback also failed: {type(rollback_exc).__name__}")
        raise
