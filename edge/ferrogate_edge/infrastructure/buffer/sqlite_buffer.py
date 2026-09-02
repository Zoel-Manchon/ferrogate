"""Buffer store-and-forward sobre SQLite.

WAL para que escribir no bloquee al reenviar. El fichero se crea con
permisos 0600: contiene telemetria firmada de un cliente y no tiene por
que ser legible por todo el sistema.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS outbox (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    topic   TEXT NOT NULL,
    payload BLOB NOT NULL,
    queued_at REAL NOT NULL DEFAULT (julianday('now'))
);

-- La secuencia anti-reenvio DEBE sobrevivir a un reinicio. Si el gateway
-- vuelve a empezar en 1, la plataforma rechaza todo por reenvio y el
-- gateway queda mudo de forma permanente sin un solo error visible.
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value INTEGER NOT NULL
);
"""


class SqliteBuffer:
    def __init__(self, path: Path, max_rows: int = 100_000) -> None:
        self._path = path
        self._max_rows = max_rows
        path.parent.mkdir(parents=True, exist_ok=True)
        new = not path.exists()
        self._db = sqlite3.connect(path, isolation_level=None)
        if new:
            os.chmod(path, 0o600)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(SCHEMA)

    def enqueue(self, topic: str, payload: bytes) -> None:
        self._db.execute(
            "INSERT INTO outbox (topic, payload) VALUES (?, ?)", (topic, payload)
        )
        # Disco lleno = gateway muerto. Se descartan los MAS ANTIGUOS:
        # en telemetria, el dato reciente vale mas que el viejo.
        self._db.execute(
            "DELETE FROM outbox WHERE id NOT IN "
            "(SELECT id FROM outbox ORDER BY id DESC LIMIT ?)",
            (self._max_rows,),
        )

    def peek(self, limit: int) -> list[tuple[int, str, bytes]]:
        rows = self._db.execute(
            "SELECT id, topic, payload FROM outbox ORDER BY id LIMIT ?", (limit,)
        ).fetchall()
        return [(r[0], r[1], r[2]) for r in rows]

    def ack(self, row_id: int) -> None:
        self._db.execute("DELETE FROM outbox WHERE id = ?", (row_id,))

    def last_sequence(self) -> int:
        row = self._db.execute(
            "SELECT value FROM meta WHERE key = 'sequence'"
        ).fetchone()
        return row[0] if row else 0

    def set_sequence(self, sequence: int) -> None:
        self._db.execute(
            "INSERT INTO meta (key, value) VALUES ('sequence', ?) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            (sequence,),
        )

    def depth(self) -> int:
        return self._db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]

    def close(self) -> None:
        self._db.close()
