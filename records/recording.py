import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class ShownRecord:
    session_id: str
    pulse: int
    position: str
    screen_id: str
    dispatch_id: int
    frame_id: int
    revision_id: int


class ShownStore:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    @staticmethod
    def install_schema(db: sqlite3.Connection) -> None:
        db.execute('''
            CREATE TABLE IF NOT EXISTS shown (
                session_id TEXT NOT NULL,
                pulse INTEGER NOT NULL CHECK (pulse >= 0),
                position TEXT NOT NULL,
                screen_id TEXT NOT NULL,
                dispatch_id INTEGER NOT NULL REFERENCES load_receipts,
                frame_id INTEGER NOT NULL REFERENCES frames,
                revision_id INTEGER NOT NULL REFERENCES art_revisions,
                PRIMARY KEY (session_id, pulse, screen_id),
                FOREIGN KEY (session_id, position) REFERENCES placements (session_id, position)
            )
        ''')

    def append_shown(self, record: ShownRecord) -> None:
        self.db.execute('''
            INSERT INTO shown (session_id, pulse, position, screen_id, dispatch_id, frame_id, revision_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (record.session_id, record.pulse, record.position, record.screen_id,
              record.dispatch_id, record.frame_id, record.revision_id))

    def list_shown(self, session_id: str, position: str | None = None) -> list[ShownRecord]:
        rows = self.db.execute('''
            SELECT shown.* FROM shown
            JOIN placements USING (session_id, position)
            WHERE shown.session_id = ? AND (? IS NULL OR shown.position = ?)
            ORDER BY shown.pulse, placements.ordinal
        ''', (session_id, position, position))
        return [ShownRecord(**row) for row in rows]
