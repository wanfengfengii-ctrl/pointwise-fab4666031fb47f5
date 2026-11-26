import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class Placement:
    session_id: str
    position: str
    screen_id: str
    name: str
    ordinal: int


class PlacementStore:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    @staticmethod
    def install_schema(db: sqlite3.Connection) -> None:
        db.execute('''
            CREATE TABLE IF NOT EXISTS placements (
                session_id TEXT NOT NULL REFERENCES sessions,
                position TEXT NOT NULL,
                screen_id TEXT NOT NULL,
                name TEXT NOT NULL,
                ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
                PRIMARY KEY (session_id, position),
                UNIQUE (session_id, screen_id),
                UNIQUE (session_id, ordinal)
            )
        ''')

    def ensure_placement(self, placement: Placement) -> None:
        self.db.execute('''
            INSERT INTO placements (session_id, position, screen_id, name, ordinal)
            VALUES (?, ?, ?, ?, ?) ON CONFLICT (session_id, position) DO NOTHING
        ''', (placement.session_id, placement.position, placement.screen_id,
              placement.name, placement.ordinal))

    def get_placement(self, session_id: str, position: str) -> Placement | None:
        row = self.db.execute('''
            SELECT * FROM placements WHERE session_id = ? AND position = ?
        ''', (session_id, position)).fetchone()
        return Placement(**row) if row is not None else None

    def list_placements(self, session_id: str) -> list[Placement]:
        rows = self.db.execute('''
            SELECT * FROM placements WHERE session_id = ? ORDER BY ordinal
        ''', (session_id,))
        return [Placement(**row) for row in rows]
