import duckdb
import pytest

from echoflow.library.duckdb_safety import atomic_duckdb_transaction


def _connection() -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(":memory:")
    connection.execute("CREATE TABLE values_for_test (value INTEGER PRIMARY KEY)")
    return connection


def test_atomic_duckdb_transaction_commits_complete_mutation() -> None:
    connection = _connection()

    with atomic_duckdb_transaction(connection):
        connection.execute("INSERT INTO values_for_test VALUES (1)")
        connection.execute("INSERT INTO values_for_test VALUES (2)")

    assert connection.execute(
        "SELECT value FROM values_for_test ORDER BY value"
    ).fetchall() == [(1,), (2,)]


def test_atomic_duckdb_transaction_rolls_back_complete_mutation() -> None:
    connection = _connection()

    with (
        pytest.raises(RuntimeError, match="forced failure"),
        atomic_duckdb_transaction(connection),
    ):
        connection.execute("INSERT INTO values_for_test VALUES (1)")
        raise RuntimeError("forced failure")

    assert connection.execute("SELECT value FROM values_for_test").fetchall() == []


def test_atomic_duckdb_transaction_rolls_back_interrupts() -> None:
    connection = _connection()

    with pytest.raises(KeyboardInterrupt), atomic_duckdb_transaction(connection):
        connection.execute("INSERT INTO values_for_test VALUES (1)")
        raise KeyboardInterrupt

    assert connection.execute("SELECT value FROM values_for_test").fetchall() == []
