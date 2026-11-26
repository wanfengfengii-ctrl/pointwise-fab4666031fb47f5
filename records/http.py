import sqlite3

from records.history import UnknownHistoryTarget, get_history


def handle_get_history(db: sqlite3.Connection, session_id: str,
                       query: dict[str, list[str]]) -> tuple[int, dict | list]:
    positions = query.get('position', [])
    if len(positions) > 1:
        return 400, {'error': 'supply at most one position'}
    try:
        return 200, get_history(db, session_id, positions[0] if positions else None)
    except UnknownHistoryTarget as error:
        return 404, {'error': str(error)}
