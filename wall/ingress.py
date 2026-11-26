import sqlite3
from dataclasses import asdict

from artwork.pixels import PixelFormatError, freeze_pixels
from composition.sheets import SheetStore
from desk.delivery import LoadReceipt, make_envelope
from desk.dispatch import DispatchStore
from wall.buffers import BufferStore


class DamagedLoad(ValueError):
    pass


class WrongScreen(ValueError):
    pass


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
        expected = asdict(make_envelope(order, frame))
        if incoming.keys() != expected.keys() or any(
            type(incoming[key]) is not type(value) or incoming[key] != value
            for key, value in expected.items()
        ):
            raise DamagedLoad('load differs from its fixed dispatch or picture')
        if screen_id != order.screen_id:
            raise WrongScreen('load was addressed to a different screen')
        buffers = BufferStore(db)
        previous = buffers.get_load_receipt(dispatch_id)
        if previous is not None:
            return previous
        receipt = LoadReceipt(dispatch_id, order.session_id, screen_id, frame.frame_id, frame.revision_id)
        buffers.save_load_receipt(receipt)
        buffers.set_standby(receipt)
        return receipt
