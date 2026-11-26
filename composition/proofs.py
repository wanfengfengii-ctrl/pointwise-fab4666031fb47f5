from dataclasses import dataclass

from artwork.catalog import ArtCatalog
from composition.sheets import Sheet, SheetStore


@dataclass(frozen=True)
class SheetProof:
    sheet: Sheet
    art_id: str

    def response(self) -> dict:
        return {
            'sheet_id': self.sheet.sheet_id,
            'revision_id': self.sheet.revision_id,
            'art_id': self.art_id,
            'left': self.sheet.left.picture(),
            'right': self.sheet.right.picture(),
        }


def get_proof(store: SheetStore, sheet_id: int) -> SheetProof | None:
    sheet = store.get_sheet(sheet_id)
    if sheet is None:
        return None
    revision = ArtCatalog(store.db).get_revision(sheet.revision_id)
    if revision is None:
        raise RuntimeError('fixed sheet has no source revision')
    return SheetProof(sheet, revision.art_id)
