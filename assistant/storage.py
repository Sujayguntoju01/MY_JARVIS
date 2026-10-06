"""SQLite storage for chat history, to-dos, notes and reminders.

Every method opens its own short-lived connection, which keeps the store safe
to use from the web server's threads and the reminder checker at once.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS todos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    due_at TEXT NOT NULL,
    delivered INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
"""


def _stamp(moment: datetime) -> str:
    """Local time as a sortable string, e.g. 2026-10-06T15:02:00."""
    return moment.replace(microsecond=0, tzinfo=None).isoformat()


class Store:
    def __init__(self, path: str | Path, clock: Callable[[], datetime] = datetime.now):
        self.path = Path(path)
        self.clock = clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:  # commits on success, rolls back on error
                yield conn
        finally:
            conn.close()

    def _now(self) -> str:
        return _stamp(self.clock())

    # ---- chat history ---------------------------------------------------

    def add_message(self, role: str, content: str) -> None:
        with self._db() as db:
            db.execute(
                "INSERT INTO messages (role, content, created_at) VALUES (?, ?, ?)",
                (role, content, self._now()),
            )

    def recent_messages(self, limit: int = 30) -> list[dict]:
        """The latest `limit` messages, oldest first."""
        with self._db() as db:
            rows = db.execute(
                "SELECT role, content, created_at FROM messages ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def clear_messages(self) -> None:
        with self._db() as db:
            db.execute("DELETE FROM messages")

    # ---- to-dos ---------------------------------------------------------

    def add_todo(self, text: str) -> int:
        with self._db() as db:
            cur = db.execute(
                "INSERT INTO todos (text, created_at) VALUES (?, ?)", (text, self._now())
            )
            return cur.lastrowid

    def list_todos(self, include_done: bool = False) -> list[dict]:
        query = "SELECT id, text, done FROM todos"
        if not include_done:
            query += " WHERE done = 0"
        with self._db() as db:
            return [dict(r) for r in db.execute(query + " ORDER BY done, id").fetchall()]

    def set_todo_done(self, todo_id: int, done: bool = True) -> bool:
        with self._db() as db:
            cur = db.execute("UPDATE todos SET done = ? WHERE id = ?", (int(done), todo_id))
            return cur.rowcount > 0

    def delete_todo(self, todo_id: int) -> bool:
        with self._db() as db:
            return db.execute("DELETE FROM todos WHERE id = ?", (todo_id,)).rowcount > 0

    # ---- notes ----------------------------------------------------------

    def add_note(self, title: str, body: str) -> int:
        with self._db() as db:
            cur = db.execute(
                "INSERT INTO notes (title, body, created_at) VALUES (?, ?, ?)",
                (title, body, self._now()),
            )
            return cur.lastrowid

    def list_notes(self, query: str = "") -> list[dict]:
        sql = "SELECT id, title, body, created_at FROM notes"
        args: tuple = ()
        if query:
            sql += " WHERE title LIKE ? OR body LIKE ?"
            args = (f"%{query}%", f"%{query}%")
        with self._db() as db:
            return [dict(r) for r in db.execute(sql + " ORDER BY id DESC", args).fetchall()]

    def delete_note(self, note_id: int) -> bool:
        with self._db() as db:
            return db.execute("DELETE FROM notes WHERE id = ?", (note_id,)).rowcount > 0

    # ---- reminders ------------------------------------------------------

    def add_reminder(self, text: str, due_at: datetime) -> int:
        with self._db() as db:
            cur = db.execute(
                "INSERT INTO reminders (text, due_at, created_at) VALUES (?, ?, ?)",
                (text, _stamp(due_at), self._now()),
            )
            return cur.lastrowid

    def list_reminders(self) -> list[dict]:
        """Reminders that have not gone off yet, soonest first."""
        with self._db() as db:
            rows = db.execute(
                "SELECT id, text, due_at FROM reminders WHERE delivered = 0 ORDER BY due_at"
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_reminder(self, reminder_id: int) -> bool:
        with self._db() as db:
            cur = db.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
            return cur.rowcount > 0

    def pop_due_reminders(self) -> list[dict]:
        """Return reminders whose time has come and mark them delivered.

        Done in one transaction so two interfaces running at once never
        announce the same reminder twice.
        """
        now = self._now()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT id, text, due_at FROM reminders "
                "WHERE delivered = 0 AND due_at <= ? ORDER BY due_at",
                (now,),
            ).fetchall()
            if rows:
                ids = [r["id"] for r in rows]
                marks = ",".join("?" * len(ids))
                db.execute(f"UPDATE reminders SET delivered = 1 WHERE id IN ({marks})", ids)
        return [dict(r) for r in rows]
