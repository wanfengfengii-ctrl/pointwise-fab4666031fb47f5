import json
import sqlite3
from dataclasses import asdict, dataclass

from desk.placements import PlacementStore
from desk.session import SessionStore
from records.recording import ShownRecord, ShownStore
from wall.buffers import BufferStore
from wall.latch import SelectedSlot, latch_selected


class UnknownSession(LookupError):
    pass


class StalePulse(ValueError):
    pass


@dataclass(frozen=True)
class PulseResult:
    session_id: str
    pulse: int
    screens: list[dict]
    shown: list[dict]


class PulseStore:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    @staticmethod
    def install_schema(db: sqlite3.Connection) -> None:
        db.execute('''
            CREATE TABLE IF NOT EXISTS pulses (
                session_id TEXT NOT NULL REFERENCES sessions,
                pulse INTEGER NOT NULL CHECK (pulse >= 0),
                result TEXT NOT NULL,
                PRIMARY KEY (session_id, pulse)
            )
        ''')

    def get_result(self, session_id: str, pulse: int) -> PulseResult | None:
        row = self.db.execute('''
            SELECT result FROM pulses WHERE session_id = ? AND pulse = ?
        ''', (session_id, pulse)).fetchone()
        return PulseResult(**json.loads(row['result'])) if row is not None else None

    def get_high_water(self, session_id: str) -> int | None:
        return self.db.execute(
            'SELECT MAX(pulse) FROM pulses WHERE session_id = ?', (session_id,),
        ).fetchone()[0]

    def save_result(self, result: PulseResult) -> None:
        self.db.execute(
            'INSERT INTO pulses (session_id, pulse, result) VALUES (?, ?, ?)',
            (result.session_id, result.pulse, json.dumps(asdict(result))),
        )


def process_pulse(db: sqlite3.Connection, session_id: str, pulse: int) -> PulseResult:
    with db:
        db.execute('BEGIN IMMEDIATE')
        if SessionStore(db).get_session(session_id) is None:
            raise UnknownSession('unknown session')
        pulses = PulseStore(db)
        original = pulses.get_result(session_id, pulse)
        if original is not None:
            return original
        high_water = pulses.get_high_water(session_id)
        if high_water is not None and pulse < high_water:
            raise StalePulse('unseen pulse is older than the latest processed pulse')
        placements = PlacementStore(db).list_placements(session_id)
        buffers = BufferStore(db)
        selections = []
        for placement in placements:
            standby = buffers.get_buffer(session_id, placement.screen_id).standby
            if standby is not None:
                selections.append(SelectedSlot(placement.screen_id, standby.dispatch_id))
        adopted = latch_selected(buffers, session_id, selections)
        records = ShownStore(db)
        screens, shown = [], []
        for placement in placements:
            screen_id = placement.screen_id
            front = buffers.get_buffer(session_id, screen_id).front
            screens.append({
                'position': placement.position,
                'screen_id': screen_id,
                'frame_id': front.frame_id if front is not None else None,
            })
            picked = adopted.get(screen_id)
            if picked is not None:
                record = ShownRecord(session_id, pulse, placement.position, screen_id,
                                     picked.dispatch_id, picked.frame_id, picked.revision_id)
                records.append_shown(record)
                shown.append(asdict(record))
        result = PulseResult(session_id, pulse, screens, shown)
        pulses.save_result(result)
        return result
