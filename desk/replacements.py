import sqlite3
from dataclasses import dataclass

from desk.placements import PlacementStore
from desk.session import SessionStore


class ReplacementConflict(ValueError):
    pass


class ReplacementTargetMissing(LookupError):
    pass


@dataclass(frozen=True)
class ScreenReplacement:
    replacement_id: int
    session_id: str
    position: str
    replacement_screen_id: str
    activation_pulse: int
    request_id: str
    activated_pulse: int | None

    @property
    def status(self) -> str:
        return 'active' if self.activated_pulse is not None else 'pending'

    def record(self) -> dict:
        return {
            'replacement_id': self.replacement_id,
            'session_id': self.session_id,
            'position': self.position,
            'replacement_screen_id': self.replacement_screen_id,
            'activation_pulse': self.activation_pulse,
            'request_id': self.request_id,
            'status': self.status,
            'activated_pulse': self.activated_pulse,
        }


def _read_replacement(row: sqlite3.Row) -> ScreenReplacement:
    return ScreenReplacement(
        row['replacement_id'], row['session_id'], row['position'],
        row['replacement_screen_id'], row['activation_pulse'], row['request_id'],
        row['activated_pulse'],
    )


class ReplacementStore:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    @staticmethod
    def install_schema(db: sqlite3.Connection) -> None:
        db.execute('''
            CREATE TABLE IF NOT EXISTS screen_replacements (
                replacement_id INTEGER PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES sessions,
                position TEXT NOT NULL,
                replacement_screen_id TEXT NOT NULL,
                activation_pulse INTEGER NOT NULL CHECK (activation_pulse >= 0),
                request_id TEXT NOT NULL,
                activated_pulse INTEGER CHECK (activated_pulse IS NULL OR activated_pulse >= 0),
                UNIQUE (session_id, request_id),
                UNIQUE (session_id),
                FOREIGN KEY (session_id, position) REFERENCES placements (session_id, position)
            )
        ''')

    def register(self, session_id: str, position: str, replacement_screen_id: str,
                 activation_pulse: int, request_id: str) -> ScreenReplacement:
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            if SessionStore(self.db).get_session(session_id) is None:
                raise ReplacementTargetMissing('unknown session')
            existing = self.db.execute('''
                SELECT * FROM screen_replacements WHERE session_id = ? AND request_id = ?
            ''', (session_id, request_id)).fetchone()
            if existing is not None:
                replacement = _read_replacement(existing)
                if (replacement.position, replacement.replacement_screen_id,
                        replacement.activation_pulse) != (position, replacement_screen_id,
                                                         activation_pulse):
                    raise ReplacementConflict(
                        'request_id already binds a different replacement')
                return replacement
            if PlacementStore(self.db).get_placement(session_id, position) is None:
                raise ReplacementTargetMissing('unknown screen position')
            if self.db.execute(
                'SELECT 1 FROM screen_replacements WHERE session_id = ?', (session_id,),
            ).fetchone() is not None:
                raise ReplacementConflict('session already has a replacement scheduled')
            if self.db.execute('''
                SELECT 1 FROM placements WHERE session_id = ? AND screen_id = ?
            ''', (session_id, replacement_screen_id)).fetchone() is not None:
                raise ReplacementConflict('replacement screen is already in use')
            high_water = self.db.execute(
                'SELECT MAX(pulse) FROM pulses WHERE session_id = ?', (session_id,),
            ).fetchone()[0]
            if high_water is not None and activation_pulse <= high_water:
                raise ReplacementConflict('planned pulse has already passed')
            replacement_id = self.db.execute('''
                INSERT INTO screen_replacements
                    (session_id, position, replacement_screen_id, activation_pulse, request_id)
                VALUES (?, ?, ?, ?, ?)
            ''', (session_id, position, replacement_screen_id, activation_pulse,
                  request_id)).lastrowid
            return ScreenReplacement(replacement_id, session_id, position, replacement_screen_id,
                                     activation_pulse, request_id, None)

    def get(self, replacement_id: int) -> ScreenReplacement | None:
        row = self.db.execute(
            'SELECT * FROM screen_replacements WHERE replacement_id = ?', (replacement_id,),
        ).fetchone()
        return _read_replacement(row) if row is not None else None

    def active_for_position(self, session_id: str, position: str) -> ScreenReplacement | None:
        row = self.db.execute('''
            SELECT * FROM screen_replacements
            WHERE session_id = ? AND position = ? AND activated_pulse IS NOT NULL
        ''', (session_id, position)).fetchone()
        return _read_replacement(row) if row is not None else None

    def due(self, session_id: str, pulse: int) -> list[ScreenReplacement]:
        rows = self.db.execute('''
            SELECT * FROM screen_replacements
            WHERE session_id = ? AND activated_pulse IS NULL AND activation_pulse <= ?
            ORDER BY replacement_id
        ''', (session_id, pulse))
        return [_read_replacement(row) for row in rows]

    def mark_activated(self, replacement_id: int, pulse: int) -> None:
        cursor = self.db.execute('''
            UPDATE screen_replacements SET activated_pulse = ?
            WHERE replacement_id = ? AND activated_pulse IS NULL
        ''', (pulse, replacement_id))
        if cursor.rowcount != 1:
            raise RuntimeError('replacement could not be activated')


def current_screen(db: sqlite3.Connection, session_id: str, position: str) -> str | None:
    replacement = ReplacementStore(db).active_for_position(session_id, position)
    if replacement is not None:
        return replacement.replacement_screen_id
    placement = PlacementStore(db).get_placement(session_id, position)
    return None if placement is None else placement.screen_id

