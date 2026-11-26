import sqlite3
from dataclasses import dataclass

from desk.delivery import LoadReceipt


@dataclass(frozen=True)
class LoadedFrame:
    dispatch_id: int
    frame_id: int
    revision_id: int


@dataclass(frozen=True)
class ScreenBuffer:
    session_id: str
    screen_id: str
    front: LoadedFrame | None
    standby: LoadedFrame | None


class BufferStore:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    @staticmethod
    def install_schema(db: sqlite3.Connection) -> None:
        db.execute('''
            CREATE TABLE IF NOT EXISTS load_receipts (
                dispatch_id INTEGER PRIMARY KEY REFERENCES dispatches,
                session_id TEXT NOT NULL,
                screen_id TEXT NOT NULL,
                frame_id INTEGER NOT NULL REFERENCES frames,
                revision_id INTEGER NOT NULL REFERENCES art_revisions,
                FOREIGN KEY (session_id, screen_id) REFERENCES placements (session_id, screen_id)
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS screen_buffers (
                session_id TEXT NOT NULL,
                screen_id TEXT NOT NULL,
                front_dispatch_id INTEGER REFERENCES load_receipts,
                standby_dispatch_id INTEGER REFERENCES load_receipts,
                PRIMARY KEY (session_id, screen_id),
                FOREIGN KEY (session_id, screen_id) REFERENCES placements (session_id, screen_id)
            )
        ''')

    def ensure_screen(self, session_id: str, screen_id: str) -> None:
        self.db.execute('''
            INSERT INTO screen_buffers (session_id, screen_id) VALUES (?, ?)
            ON CONFLICT (session_id, screen_id) DO NOTHING
        ''', (session_id, screen_id))

    def get_buffer(self, session_id: str, screen_id: str) -> ScreenBuffer:
        row = self.db.execute('''
            SELECT * FROM screen_buffers WHERE session_id = ? AND screen_id = ?
        ''', (session_id, screen_id)).fetchone()
        if row is None:
            raise RuntimeError('configured screen has no buffer')
        return ScreenBuffer(session_id, screen_id, self._loaded(row['front_dispatch_id']),
                            self._loaded(row['standby_dispatch_id']))

    def _loaded(self, dispatch_id: int | None) -> LoadedFrame | None:
        if dispatch_id is None:
            return None
        receipt = self.get_load_receipt(dispatch_id)
        if receipt is None:
            raise RuntimeError('buffer references a missing load receipt')
        return LoadedFrame(receipt.dispatch_id, receipt.frame_id, receipt.revision_id)

    def set_standby(self, receipt: LoadReceipt) -> None:
        cursor = self.db.execute('''
            UPDATE screen_buffers SET standby_dispatch_id = ?
            WHERE session_id = ? AND screen_id = ?
        ''', (receipt.dispatch_id, receipt.session_id, receipt.screen_id))
        if cursor.rowcount != 1:
            raise RuntimeError('load target has no buffer')

    def get_load_receipt(self, dispatch_id: int) -> LoadReceipt | None:
        row = self.db.execute(
            'SELECT * FROM load_receipts WHERE dispatch_id = ?', (dispatch_id,),
        ).fetchone()
        return LoadReceipt(**row) if row is not None else None

    def save_load_receipt(self, receipt: LoadReceipt) -> None:
        self.db.execute('''
            INSERT INTO load_receipts (dispatch_id, session_id, screen_id, frame_id, revision_id)
            VALUES (?, ?, ?, ?, ?)
        ''', (receipt.dispatch_id, receipt.session_id, receipt.screen_id,
              receipt.frame_id, receipt.revision_id))

    def promote(self, session_id: str, screen_id: str, dispatch_id: int) -> bool:
        cursor = self.db.execute('''
            UPDATE screen_buffers SET front_dispatch_id = standby_dispatch_id, standby_dispatch_id = NULL
            WHERE session_id = ? AND screen_id = ? AND standby_dispatch_id = ?
        ''', (session_id, screen_id, dispatch_id))
        return cursor.rowcount == 1
