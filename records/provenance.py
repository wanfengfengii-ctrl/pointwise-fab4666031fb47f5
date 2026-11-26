import sqlite3
from dataclasses import dataclass

from artwork.catalog import ArtCatalog
from composition.sheets import SheetStore
from records.recording import ShownRecord


@dataclass(frozen=True)
class FrameProvenance:
    art_id: str
    revision_id: int
    sheet_id: int
    side: str
    viewport: list[int]


def resolve_provenance(db: sqlite3.Connection, record: ShownRecord) -> FrameProvenance:
    frame = SheetStore(db).get_frame(record.frame_id)
    if frame is None or frame.revision_id != record.revision_id:
        raise RuntimeError('shown frame and revision do not match')
    revision = ArtCatalog(db).get_revision(record.revision_id)
    if revision is None:
        raise RuntimeError('shown revision is missing')
    return FrameProvenance(revision.art_id, revision.revision_id, frame.sheet_id,
                           frame.side, frame.viewport.bounds())
