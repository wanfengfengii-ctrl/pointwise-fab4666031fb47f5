import sqlite3
from dataclasses import asdict

from desk.placements import PlacementStore
from desk.session import SessionStore
from records.provenance import resolve_provenance
from records.recording import ShownStore


class UnknownHistoryTarget(LookupError):
    pass


def get_history(db: sqlite3.Connection, session_id: str, position: str | None = None) -> list[dict]:
    if SessionStore(db).get_session(session_id) is None:
        raise UnknownHistoryTarget('unknown session')
    if position is not None and PlacementStore(db).get_placement(session_id, position) is None:
        raise UnknownHistoryTarget('unknown screen position')
    results = []
    for record in ShownStore(db).list_shown(session_id, position):
        results.append({**asdict(record), 'source': asdict(resolve_provenance(db, record))})
    return results
