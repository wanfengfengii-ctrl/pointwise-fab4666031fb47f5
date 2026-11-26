import sqlite3
from dataclasses import dataclass

from composition.sheets import SheetStore
from desk.placements import PlacementStore
from desk.replacements import current_screen
from desk.session import SessionStore


class DispatchConflict(ValueError):
    pass


class DispatchTargetMissing(LookupError):
    pass


@dataclass(frozen=True)
class DispatchOrder:
    dispatch_id: int
    session_id: str
    request_id: str
    position: str
    screen_id: str
    frame_id: int
    status: str
    target_screen_id: str | None = None

    def record(self) -> dict:
        return {
            'dispatch_id': self.dispatch_id,
            'session_id': self.session_id,
            'request_id': self.request_id,
            'position': self.position,
            'screen_id': self.screen_id,
            'frame_id': self.frame_id,
            'status': self.status,
        }


def _read_order(row: sqlite3.Row) -> DispatchOrder:
    return DispatchOrder(
        row['dispatch_id'], row['session_id'], row['request_id'], row['position'],
        row['screen_id'], row['frame_id'], 'confirmed' if row['confirmed'] else 'pending',
        row['target_screen_id'] or row['screen_id'],
    )


class DispatchStore:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    @staticmethod
    def install_schema(db: sqlite3.Connection) -> None:
        db.execute('''
            CREATE TABLE IF NOT EXISTS dispatches (
                dispatch_id INTEGER PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES sessions,
                request_id TEXT NOT NULL,
                position TEXT NOT NULL,
                screen_id TEXT NOT NULL,
                frame_id INTEGER NOT NULL REFERENCES frames,
                confirmed INTEGER NOT NULL DEFAULT 0 CHECK (confirmed IN (0, 1)),
                target_screen_id TEXT,
                UNIQUE (session_id, request_id),
                FOREIGN KEY (session_id, position) REFERENCES placements (session_id, position),
                FOREIGN KEY (session_id, screen_id) REFERENCES screen_devices (session_id, screen_id)
            )
        ''')
        columns = {row['name'] for row in db.execute('PRAGMA table_info(dispatches)')}
        if 'target_screen_id' not in columns:
            db.execute('ALTER TABLE dispatches ADD COLUMN target_screen_id TEXT')
            db.execute('UPDATE dispatches SET target_screen_id = screen_id')

    def register(self, session_id: str, position: str, frame_id: int,
                 request_id: str) -> DispatchOrder:
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            row = self.db.execute('''
                SELECT * FROM dispatches WHERE session_id = ? AND request_id = ?
            ''', (session_id, request_id)).fetchone()
            if row is not None:
                original = _read_order(row)
                if (position, frame_id) != (original.position, original.frame_id):
                    raise DispatchConflict('request_id already binds a different screen position or frame')
                return original
            if SessionStore(self.db).get_session(session_id) is None:
                raise DispatchTargetMissing('unknown session')
            placement = PlacementStore(self.db).get_placement(session_id, position)
            if placement is None:
                raise DispatchTargetMissing('unknown screen position')
            if SheetStore(self.db).get_frame(frame_id) is None:
                raise DispatchTargetMissing('unknown frame')
            screen_id = current_screen(self.db, session_id, position) or placement.screen_id
            dispatch_id = self.db.execute('''
                INSERT INTO dispatches
                    (session_id, request_id, position, screen_id, frame_id, target_screen_id)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (session_id, request_id, position, screen_id, frame_id, screen_id)).lastrowid
            return DispatchOrder(dispatch_id, session_id, request_id, position,
                                 screen_id, frame_id, 'pending', screen_id)

    def get_dispatch(self, dispatch_id: int) -> DispatchOrder | None:
        row = self.db.execute(
            'SELECT * FROM dispatches WHERE dispatch_id = ?', (dispatch_id,),
        ).fetchone()
        return _read_order(row) if row is not None else None

    def retarget_position(self, session_id: str, position: str, screen_id: str) -> None:
        self.db.execute('''
            UPDATE dispatches SET target_screen_id = ?
            WHERE session_id = ? AND position = ?
              AND dispatch_id NOT IN (SELECT dispatch_id FROM load_receipts)
        ''', (screen_id, session_id, position))

    def confirm_load(self, dispatch_id: int, session_id: str, screen_id: str, frame_id: int) -> bool:
        cursor = self.db.execute('''
            UPDATE dispatches SET confirmed = 1
            WHERE dispatch_id = ? AND session_id = ? AND frame_id = ?
              AND ? IN (screen_id, COALESCE(target_screen_id, screen_id))
        ''', (dispatch_id, session_id, frame_id, screen_id))
        return cursor.rowcount == 1
