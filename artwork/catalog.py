import json
import sqlite3
from dataclasses import dataclass

from artwork.pixels import PixelGrid, freeze_pixels, pixel_dimensions


@dataclass(frozen=True)
class ArtRevision:
    revision_id: int
    art_id: str
    width: int
    height: int
    pixels: PixelGrid


class ArtCatalog:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    @staticmethod
    def install_schema(db: sqlite3.Connection) -> None:
        db.execute('''
            CREATE TABLE IF NOT EXISTS art_revisions (
                revision_id INTEGER PRIMARY KEY,
                art_id TEXT NOT NULL,
                width INTEGER NOT NULL CHECK (width > 0),
                height INTEGER NOT NULL CHECK (height > 0),
                pixels TEXT NOT NULL
            )
        ''')

    def append_revision(self, art_id: str, pixels: PixelGrid) -> ArtRevision:
        width, height = pixel_dimensions(pixels)
        with self.db:
            cursor = self.db.execute(
                'INSERT INTO art_revisions (art_id, width, height, pixels) VALUES (?, ?, ?, ?)',
                (art_id, width, height, json.dumps(pixels)),
            )
        return ArtRevision(cursor.lastrowid, art_id, width, height, pixels)

    def get_revision(self, revision_id: int) -> ArtRevision | None:
        row = self.db.execute(
            'SELECT * FROM art_revisions WHERE revision_id = ?', (revision_id,),
        ).fetchone()
        if row is None:
            return None
        return ArtRevision(
            row['revision_id'], row['art_id'], row['width'], row['height'],
            freeze_pixels(json.loads(row['pixels'])),
        )
