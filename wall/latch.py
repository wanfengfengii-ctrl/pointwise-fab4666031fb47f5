from collections.abc import Iterable
from dataclasses import dataclass

from wall.buffers import BufferStore, LoadedFrame


@dataclass(frozen=True)
class SelectedSlot:
    screen_id: str
    dispatch_id: int


class SlotSelectionError(ValueError):
    pass


def latch_selected(buffers: BufferStore, session_id: str,
                   slots: Iterable[SelectedSlot]) -> dict[str, LoadedFrame]:
    if not buffers.db.in_transaction:
        raise SlotSelectionError('latching requires an active pulse transaction')
    adopted = {}
    for selection in slots:
        if selection.screen_id in adopted:
            raise SlotSelectionError('a screen can only be selected once')
        standby = buffers.get_buffer(session_id, selection.screen_id).standby
        if standby is None or standby.dispatch_id != selection.dispatch_id:
            raise SlotSelectionError('selected standby is no longer current')
        adopted[selection.screen_id] = standby
    for screen_id, standby in adopted.items():
        if not buffers.promote(session_id, screen_id, standby.dispatch_id):
            raise SlotSelectionError('selected standby could not be promoted')
    return adopted
