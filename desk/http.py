from collections.abc import Callable
from dataclasses import asdict

from composition.sheets import SheetStore
from desk.delivery import LoadEnvelope, deliver_order
from desk.dispatch import DispatchConflict, DispatchStore, DispatchTargetMissing
from desk.placements import PlacementStore
from desk.replacements import current_screen
from desk.session import SessionStore, is_label


def handle_dispatch(store: DispatchStore, body: object,
                    send: Callable[[LoadEnvelope], object]) -> tuple[int, dict]:
    if not isinstance(body, dict):
        return 400, {'error': 'expected a dispatch object'}
    session_id = body.get('session_id')
    position = body.get('position')
    request_id = body.get('request_id')
    frame_id = body.get('frame_id')
    if not all(is_label(label) for label in (session_id, position, request_id)):
        return 400, {'error': 'session_id, position and request_id must be printable strings'}
    if type(frame_id) is not int or not 1 <= frame_id <= 2**63 - 1:
        return 400, {'error': 'frame_id must be a positive integer'}
    try:
        order = store.register(session_id, position, frame_id, request_id)
    except DispatchTargetMissing as error:
        return 404, {'error': str(error)}
    except DispatchConflict as error:
        return 409, {'error': str(error)}
    if order.status == 'pending':
        deliver_order(order, SheetStore(store.db), send)
    return handle_get_dispatch(store, order.dispatch_id)


def handle_get_dispatch(store: DispatchStore, dispatch_id: int) -> tuple[int, dict]:
    order = store.get_dispatch(dispatch_id)
    if order is None:
        return 404, {'error': 'unknown dispatch'}
    return 200, order.record()


def handle_session(sessions: SessionStore, session_id: str) -> tuple[int, dict]:
    session = sessions.get_session(session_id)
    if session is None:
        return 404, {'error': 'unknown session'}
    placements = PlacementStore(sessions.db).list_placements(session_id)
    return 200, {**asdict(session), 'placements': [
        {**asdict(item),
         'screen_id': current_screen(sessions.db, session_id, item.position) or item.screen_id}
        for item in placements
    ]}
