import json
import sqlite3
from pathlib import Path

from artwork.catalog import ArtCatalog
from composition.sheets import SheetStore
from desk.dispatch import DispatchStore
from desk.placements import Placement, PlacementStore
from desk.replacements import ReplacementStore
from desk.session import Session, SessionStore, is_label
from records.recording import ShownStore
from wall.buffers import BufferStore
from wall.pulses import PulseStore


def seed_session(db: sqlite3.Connection, document: object) -> None:
    if not db.in_transaction:
        raise RuntimeError('seeding requires an active transaction')
    if not isinstance(document, dict):
        raise ValueError('seed must be an object')
    session_id = document.get('session_id')
    name = document.get('name')
    entries = document.get('placements')
    if not is_label(session_id) or not is_label(name) or not isinstance(entries, list) or not entries:
        raise ValueError('seed requires a session, name and at least one placement')
    placements = []
    for ordinal, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError('placement must be an object')
        position, screen_id, screen_name = (entry.get(key) for key in ('position', 'screen_id', 'name'))
        if not all(is_label(value) for value in (position, screen_id, screen_name)):
            raise ValueError('placement requires a position, screen_id and name')
        placements.append(Placement(session_id, position, screen_id, screen_name, ordinal))
    if len({item.position for item in placements}) != len(placements):
        raise ValueError('seed positions must be unique')
    if len({item.screen_id for item in placements}) != len(placements):
        raise ValueError('seed screens must be unique')
    SessionStore(db).ensure_session(Session(session_id, name))
    store = PlacementStore(db)
    buffers = BufferStore(db)
    for item in placements:
        store.ensure_placement(item)
        installed = store.get_placement(session_id, item.position)
        store.ensure_device(session_id, installed.screen_id)
        buffers.ensure_screen(session_id, installed.screen_id)


def initialize_database(db: sqlite3.Connection, seed_path: Path) -> None:
    with db:
        db.execute('BEGIN IMMEDIATE')
        for owner in (ArtCatalog, SheetStore, SessionStore, PlacementStore, DispatchStore,
                      BufferStore, PulseStore, ShownStore, ReplacementStore):
            owner.install_schema(db)
        db.execute('''
            INSERT INTO screen_devices (session_id, screen_id)
            SELECT session_id, screen_id FROM placements
            WHERE NOT EXISTS (
                SELECT 1 FROM screen_devices
                WHERE screen_devices.session_id = placements.session_id
                  AND screen_devices.screen_id = placements.screen_id
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS initialization (
                complete INTEGER PRIMARY KEY CHECK (complete = 1)
            )
        ''')
        if db.execute('SELECT complete FROM initialization WHERE complete = 1').fetchone() is None:
            seed_session(db, json.loads(seed_path.read_text(encoding='utf-8')))
            db.execute('INSERT INTO initialization (complete) VALUES (1)')
