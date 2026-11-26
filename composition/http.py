from composition.proofs import get_proof
from composition.sheets import SheetStore, UnknownRevision
from composition.viewports import ViewportError


def handle_create_sheet(store: SheetStore, body: object) -> tuple[int, dict]:
    if not isinstance(body, dict):
        return 400, {'error': 'expected a sheet object'}
    revision_id = body.get('revision_id')
    if type(revision_id) is not int or not 1 <= revision_id <= 2**63 - 1:
        return 400, {'error': 'revision_id must be a positive integer'}
    try:
        sheet = store.create_sheet(revision_id, body.get('left'), body.get('right'))
    except UnknownRevision as error:
        return 404, {'error': str(error)}
    except ViewportError as error:
        return 400, {'error': str(error)}
    return 200, {
        'sheet_id': sheet.sheet_id,
        'left_frame_id': sheet.left.frame_id,
        'right_frame_id': sheet.right.frame_id,
    }


def handle_get_proof(store: SheetStore, sheet_id: int) -> tuple[int, dict]:
    proof = get_proof(store, sheet_id)
    if proof is None:
        return 404, {'error': 'unknown sheet'}
    return 200, proof.response()
