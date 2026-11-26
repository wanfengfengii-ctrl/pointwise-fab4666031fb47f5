import argparse
import json
import sqlite3
from collections.abc import Callable
from contextlib import closing
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

from artwork.catalog import ArtCatalog
from artwork.http import handle_get_revision, handle_import_art
from composition.http import handle_create_sheet, handle_get_proof
from composition.sheets import SheetStore
from desk.bootstrap import initialize_database
from desk.delivery import LoadEnvelope, LoadReceipt, acknowledge_load
from desk.dispatch import DispatchStore
from desk.http import handle_dispatch, handle_get_dispatch, handle_session
from desk.session import SessionStore
from records.http import handle_get_history
from wall.buffers import BufferStore
from wall.http import handle_front, handle_load, handle_pulse

DEFAULT_SEED = Path(__file__).resolve().parents[1] / 'samples' / 'session.json'


def _identity(segment: str) -> int | None:
    if len(segment) <= 19 and segment.isascii() and segment.isdecimal():
        number = int(segment)
        if 1 <= number <= 2**63 - 1:
            return number
    return None


class Application:
    def __init__(self, db_path: Path, send_load: Callable | None, send_receipt: Callable | None):
        self.db_path = db_path
        self.send_load = self._send_local if send_load is None else send_load
        self.send_receipt = self.acknowledge if send_receipt is None else send_receipt

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys = ON')
        return db

    def _send_local(self, envelope: LoadEnvelope) -> None:
        path = '/screens/' + quote(envelope.screen_id, safe='') + '/loads'
        status, result = self.request('POST', path, asdict(envelope))
        if status != 200:
            raise RuntimeError(f'local delivery rejected: {result}')

    def acknowledge(self, receipt: LoadReceipt) -> bool:
        with closing(self.connect()) as db:
            return acknowledge_load(DispatchStore(db), receipt, BufferStore(db).get_load_receipt)

    def request(self, method: str, target: str, body: object = None) -> tuple[int, dict | list]:
        try:
            url = urlsplit(target)
            parts = [unquote(part, errors='strict') for part in url.path.split('/')[1:]]
            query = parse_qs(url.query, keep_blank_values=True, errors='strict')
        except ValueError:
            return 400, {'error': 'malformed request target'}
        with closing(self.connect()) as db:
            match method, parts:
                case 'POST', ['artwork']:
                    return handle_import_art(ArtCatalog(db), body)
                case 'GET', ['artwork', number] if (revision_id := _identity(number)) is not None:
                    return handle_get_revision(ArtCatalog(db), revision_id)
                case 'POST', ['sheets']:
                    return handle_create_sheet(SheetStore(db), body)
                case 'GET', ['sheets', number] if (sheet_id := _identity(number)) is not None:
                    return handle_get_proof(SheetStore(db), sheet_id)
                case 'POST', ['dispatches']:
                    return handle_dispatch(DispatchStore(db), body, self.send_load)
                case 'GET', ['dispatches', number] if (dispatch_id := _identity(number)) is not None:
                    return handle_get_dispatch(DispatchStore(db), dispatch_id)
                case 'POST', ['screens', screen_id, 'loads']:
                    return handle_load(db, screen_id, body, self.send_receipt)
                case 'POST', ['pulses']:
                    return handle_pulse(db, body)
                case 'GET', ['sessions', session_id]:
                    return handle_session(SessionStore(db), session_id)
                case 'GET', ['sessions', session_id, 'screens', position]:
                    return handle_front(db, session_id, position)
                case 'GET', ['sessions', session_id, 'shown']:
                    return handle_get_history(db, session_id, query)
        return 404, {'error': 'unknown endpoint'}


def build_application(db_path: str | Path, seed_path: str | Path = DEFAULT_SEED, *,
                      send_load: Callable | None = None,
                      send_receipt: Callable | None = None) -> Application:
    app = Application(Path(db_path), send_load, send_receipt)
    with closing(app.connect()) as db:
        initialize_database(db, Path(seed_path))
    return app


def _reject_constant(value: str) -> None:
    raise ValueError(f'invalid JSON constant {value}')


def serve(app: Application, port: int = 8000) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self._route()

        def do_POST(self) -> None:
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if size <= 0:
                    raise ValueError('missing JSON body')
                body = json.loads(self.rfile.read(size), parse_constant=_reject_constant)
            except (ValueError, OverflowError, RecursionError):
                self._reply(400, {'error': 'malformed JSON body'})
                return
            self._route(body)

        def _route(self, body: object = None) -> None:
            try:
                status, payload = app.request(self.command, self.path, body)
            except Exception as error:
                self.log_error('%s: %s', type(error).__name__, error)
                status, payload = 500, {'error': 'operation failed'}
            self._reply(status, payload)

        def _reply(self, status: int, payload: dict | list) -> None:
            data = json.dumps(payload, allow_nan=False).encode('utf-8')
            try:
                self.send_response(status)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                return

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main() -> None:
    parser = argparse.ArgumentParser(description='Museum exhibition playout server')
    parser.add_argument('--db', required=True, type=Path)
    parser.add_argument('--seed', type=Path, default=DEFAULT_SEED)
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    app = build_application(args.db, args.seed)
    with serve(app, args.port) as server:
        print(f'Listening on 127.0.0.1:{server.server_port}', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            return


if __name__ == '__main__':
    main()
