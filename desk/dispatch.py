import sqlite3
from dataclasses import dataclass

from composition.sheets import SheetStore
from desk.placements import PlacementStore
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


def _read_order(row: sqlite3.Row) -> DispatchOrder:
    return DispatchOrder(
        row['dispatch_id'], row['session_id'], row['request_id'], row['position'],
        row['screen_id'], row['frame_id'], 'confirmed' if row['confirmed'] else 'pending',
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
                UNIQUE (session_id, request_id),
                FOREIGN KEY (session_id, position) REFERENCES placements (session_id, position),
                FOREIGN KEY (session_id, screen_id) REFERENCES placements (session_id, screen_id)
            )
        ''')

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
            dispatch_id = self.db.execute('''
                INSERT INTO dispatches (session_id, request_id, position, screen_id, frame_id)
                VALUES (?, ?, ?, ?, ?)
            ''', (session_id, request_id, position, placement.screen_id, frame_id)).lastrowid
            return DispatchOrder(dispatch_id, session_id, request_id, position,
                                 placement.screen_id, frame_id, 'pending')

    def get_dispatch(self, dispatch_id: int) -> DispatchOrder | None:
        row = self.db.execute(
            'SELECT * FROM dispatches WHERE dispatch_id = ?', (dispatch_id,),
        ).fetchone()
        return _read_order(row) if row is not None else None

    def confirm_load(self, dispatch_id: int, session_id: str, screen_id: str, frame_id: int) -> bool:
        cursor = self.db.execute('''
            UPDATE dispatches SET confirmed = 1
            WHERE dispatch_id = ? AND session_id = ? AND screen_id = ? AND frame_id = ?
        ''', (dispatch_id, session_id, screen_id, frame_id))
        return cursor.rowcount == 1
