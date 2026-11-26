from collections.abc import Callable
from dataclasses import dataclass

from artwork.pixels import PixelGrid
from composition.sheets import Frame, SheetStore
from desk.dispatch import DispatchOrder, DispatchStore


@dataclass(frozen=True)
class LoadEnvelope:
    dispatch_id: int
    session_id: str
    position: str
    screen_id: str
    frame_id: int
    revision_id: int
    width: int
    height: int
    pixels: PixelGrid


@dataclass(frozen=True)
class LoadReceipt:
    dispatch_id: int
    session_id: str
    screen_id: str
    frame_id: int
    revision_id: int


def make_envelope(order: DispatchOrder, frame: Frame) -> LoadEnvelope:
    if frame.frame_id != order.frame_id:
        raise ValueError('frame does not match dispatch')
    screen_id = order.target_screen_id or order.screen_id
    return LoadEnvelope(
        order.dispatch_id, order.session_id, order.position, screen_id,
        frame.frame_id, frame.revision_id, frame.viewport.width, frame.viewport.height, frame.pixels,
    )


def deliver_order(order: DispatchOrder, sheets: SheetStore,
                  send: Callable[[LoadEnvelope], object]) -> None:
    frame = sheets.get_frame(order.frame_id)
    if frame is None:
        raise RuntimeError('dispatch has no fixed frame')
    send(make_envelope(order, frame))


def acknowledge_load(dispatches: DispatchStore, receipt: LoadReceipt,
                     get_receipt: Callable[[int], LoadReceipt | None]) -> bool:
    with dispatches.db:
        dispatches.db.execute('BEGIN IMMEDIATE')
        if get_receipt(receipt.dispatch_id) != receipt:
            return False
        return dispatches.confirm_load(
            receipt.dispatch_id, receipt.session_id, receipt.screen_id, receipt.frame_id,
        )
