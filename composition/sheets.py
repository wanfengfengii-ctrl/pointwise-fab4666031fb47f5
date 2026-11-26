import json
import sqlite3
from dataclasses import dataclass

from artwork.catalog import ArtCatalog
from artwork.pixels import PixelGrid, freeze_pixels
from composition.render import render_viewport
from composition.viewports import Viewport, validate_viewport


class UnknownRevision(LookupError):
    pass


@dataclass(frozen=True)
class Frame:
    frame_id: int
    sheet_id: int
    revision_id: int
    side: str
    viewport: Viewport
    pixels: PixelGrid

    def picture(self) -> dict:
        return {
            'frame_id': self.frame_id,
            'sheet_id': self.sheet_id,
            'revision_id': self.revision_id,
            'side': self.side,
            'viewport': self.viewport.bounds(),
            'width': self.viewport.width,
            'height': self.viewport.height,
            'pixels': self.pixels,
        }


@dataclass(frozen=True)
class Sheet:
    sheet_id: int
    revision_id: int
    left: Frame
    right: Frame


def _read_frame(row: sqlite3.Row) -> Frame:
    return Frame(
        row['frame_id'], row['sheet_id'], row['revision_id'], row['side'],
        Viewport(*json.loads(row['viewport'])), freeze_pixels(json.loads(row['pixels'])),
    )


class SheetStore:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    @staticmethod
    def install_schema(db: sqlite3.Connection) -> None:
        db.execute('''
            CREATE TABLE IF NOT EXISTS sheets (
                sheet_id INTEGER PRIMARY KEY,
                revision_id INTEGER NOT NULL REFERENCES art_revisions
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS frames (
                frame_id INTEGER PRIMARY KEY,
                sheet_id INTEGER NOT NULL REFERENCES sheets,
                side TEXT NOT NULL CHECK (side IN ('left', 'right')),
                viewport TEXT NOT NULL,
                pixels TEXT NOT NULL,
                UNIQUE (sheet_id, side)
            )
        ''')

    def create_sheet(self, revision_id: int, left: object, right: object) -> Sheet:
        revision = ArtCatalog(self.db).get_revision(revision_id)
        if revision is None:
            raise UnknownRevision('unknown revision')
        viewports = {
            'left': validate_viewport(left, revision.width, revision.height),
            'right': validate_viewport(right, revision.width, revision.height),
        }
        pictures = {
            side: render_viewport(revision.pixels, viewport)
            for side, viewport in viewports.items()
        }
        frames = {}
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            sheet_id = self.db.execute(
                'INSERT INTO sheets (revision_id) VALUES (?)', (revision_id,),
            ).lastrowid
            for side, viewport in viewports.items():
                pixels = pictures[side]
                frame_id = self.db.execute(
                    'INSERT INTO frames (sheet_id, side, viewport, pixels) VALUES (?, ?, ?, ?)',
                    (sheet_id, side, json.dumps(viewport.bounds()), json.dumps(pixels)),
                ).lastrowid
                frames[side] = Frame(frame_id, sheet_id, revision_id, side, viewport, pixels)
        return Sheet(sheet_id, revision_id, frames['left'], frames['right'])

    def get_sheet(self, sheet_id: int) -> Sheet | None:
        rows = self.db.execute('''
            SELECT f.*, s.revision_id FROM frames AS f JOIN sheets AS s USING (sheet_id)
            WHERE f.sheet_id = ?
        ''', (sheet_id,)).fetchall()
        if not rows:
            return None
        frames = {row['side']: _read_frame(row) for row in rows}
        return Sheet(sheet_id, rows[0]['revision_id'], frames['left'], frames['right'])

    def get_frame(self, frame_id: int) -> Frame | None:
        row = self.db.execute('''
            SELECT f.*, s.revision_id FROM frames AS f JOIN sheets AS s USING (sheet_id)
            WHERE f.frame_id = ?
        ''', (frame_id,)).fetchone()
        return _read_frame(row) if row is not None else None
