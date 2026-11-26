import sqlite3
from dataclasses import asdict, replace

from artwork.pixels import PixelFormatError, freeze_pixels
from composition.sheets import SheetStore
from desk.delivery import LoadReceipt, make_envelope
from desk.dispatch import DispatchStore
from wall.buffers import BufferStore


class DamagedLoad(ValueError):
    pass


class WrongScreen(ValueError):
    pass


def _matches(incoming: dict, expected: dict) -> bool:
    return incoming.keys() == expected.keys() and all(
        type(incoming[key]) is type(value) and incoming[key] == value
        for key, value in expected.items()
    )


def _store(buffers: BufferStore, order, frame, screen_id: str) -> LoadReceipt:
    receipt = LoadReceipt(order.dispatch_id, order.session_id, screen_id,
                          frame.frame_id, frame.revision_id)
    buffers.save_load_receipt(receipt)
    buffers.set_standby(receipt)
    return receipt


def receive_load(db: sqlite3.Connection, screen_id: str, payload: object) -> LoadReceipt:
    if not isinstance(payload, dict):
        raise DamagedLoad('expected a load object')
    dispatch_id = payload.get('dispatch_id')
    if type(dispatch_id) is not int or not 1 <= dispatch_id <= 2**63 - 1:
        raise DamagedLoad('invalid dispatch_id in load')
    try:
        pixels = freeze_pixels(payload.get('pixels'))
    except PixelFormatError as error:
        raise DamagedLoad(str(error)) from error
    incoming = {**payload, 'pixels': pixels}
    with db:
        db.execute('BEGIN IMMEDIATE')
        order = DispatchStore(db).get_dispatch(dispatch_id)
        if order is None:
            raise DamagedLoad('load does not identify a registered dispatch')
        frame = SheetStore(db).get_frame(order.frame_id)
        if frame is None:
            raise RuntimeError('dispatch frame is missing')
        buffers = BufferStore(db)
        previous = buffers.get_load_receipt(dispatch_id)
        target = order.target_screen_id or order.screen_id
        if _matches(incoming, asdict(make_envelope(order, frame))):
            if screen_id != target:
                raise WrongScreen('load was addressed to a different screen')
            if previous is not None:
                return previous
            return _store(buffers, order, frame, screen_id)
        if target != order.screen_id and _matches(
            incoming, asdict(make_envelope(replace(order, target_screen_id=order.screen_id), frame))
        ):
            if previous is not None and screen_id == previous.screen_id:
                return previous
            raise WrongScreen('load belongs to the former screen after replacement')
        raise DamagedLoad('load differs from its fixed dispatch or picture')
