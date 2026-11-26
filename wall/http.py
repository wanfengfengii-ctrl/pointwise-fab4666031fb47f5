import sqlite3
from collections.abc import Callable
from dataclasses import asdict

from composition.sheets import SheetStore
from desk.delivery import LoadReceipt
from desk.placements import PlacementStore
from desk.session import SessionStore, is_label
from wall.buffers import BufferStore
from wall.ingress import DamagedLoad, WrongScreen, receive_load
from wall.pulses import StalePulse, UnknownSession, process_pulse


def handle_load(db: sqlite3.Connection, screen_id: str, body: object,
                return_receipt: Callable[[LoadReceipt], object]) -> tuple[int, dict]:
    try:
        receipt = receive_load(db, screen_id, body)
    except DamagedLoad as error:
        return 400, {'error': str(error)}
    except WrongScreen as error:
        return 409, {'error': str(error)}
    return_receipt(receipt)
    return 200, asdict(receipt)


def handle_pulse(db: sqlite3.Connection, body: object) -> tuple[int, dict]:
    if not isinstance(body, dict) or not is_label(body.get('session_id')):
        return 400, {'error': 'expected a pulse object with session_id'}
    pulse = body.get('pulse')
    if type(pulse) is not int or not 0 <= pulse <= 2**63 - 1:
        return 400, {'error': 'pulse must be a nonnegative integer'}
    try:
        result = process_pulse(db, body['session_id'], pulse)
    except UnknownSession as error:
        return 404, {'error': str(error)}
    except StalePulse as error:
        return 409, {'error': str(error)}
    return 200, asdict(result)


def handle_front(db: sqlite3.Connection, session_id: str, position: str) -> tuple[int, dict]:
    if SessionStore(db).get_session(session_id) is None:
        return 404, {'error': 'unknown session'}
    placement = PlacementStore(db).get_placement(session_id, position)
    if placement is None:
        return 404, {'error': 'unknown screen position'}
    front = BufferStore(db).get_buffer(session_id, placement.screen_id).front
    picture = None
    if front is not None:
        frame = SheetStore(db).get_frame(front.frame_id)
        if frame is None:
            raise RuntimeError('front has no fixed frame')
        picture = {**frame.picture(), 'dispatch_id': front.dispatch_id}
    return 200, {'position': position, 'screen_id': placement.screen_id, 'front': picture}
