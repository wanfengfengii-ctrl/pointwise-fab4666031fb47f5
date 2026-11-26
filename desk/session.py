import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class Session:
    session_id: str
    name: str


def is_label(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value.isprintable()


class SessionStore:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    @staticmethod
    def install_schema(db: sqlite3.Connection) -> None:
        db.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY NOT NULL,
                name TEXT NOT NULL
            )
        ''')

    def ensure_session(self, session: Session) -> None:
        self.db.execute('''
            INSERT INTO sessions (session_id, name) VALUES (?, ?)
            ON CONFLICT (session_id) DO NOTHING
        ''', (session.session_id, session.name))

    def get_session(self, session_id: str) -> Session | None:
        row = self.db.execute(
            'SELECT session_id, name FROM sessions WHERE session_id = ?', (session_id,),
        ).fetchone()
        return Session(**row) if row is not None else None
