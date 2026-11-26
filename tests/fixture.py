import json
import unittest
from contextlib import closing
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from desk.server import build_application, serve

SESSION = 'gallery-day'
SESSION_PATH = f'/sessions/{SESSION}'
ART = [[[1, 2, 3], [4, 5, 6]], [[7, 8, 9], [10, 11, 12]]]
LEFT = [0, 0, 1, 2]
RIGHT = [1, 0, 2, 2]


def http_request(base, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = Request(base + path, data=data, headers={'Content-Type': 'application/json'})
    try:
        response = urlopen(request, timeout=5)
    except HTTPError as error:
        response = error
    with response:
        return response.code, json.load(response)


class WallTestCase(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.db_path = Path(directory.name) / 'wall.sqlite3'
        self.envelopes = []
        self.receipts = []
        self.hold_loads = False
        self.hold_receipts = False
        self.server = None
        self.start()
        self.addCleanup(self.stop)

    def start(self):
        self.app = build_application(self.db_path, send_receipt=self._receipt)
        self.local_send = self.app.send_load
        self.app.send_load = self._send
        self.server = serve(self.app, 0)
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.thread = Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.01})
        self.thread.start()

    def stop(self):
        if self.server is not None:
            self.server.shutdown()
            self.thread.join()
            self.server.server_close()
            self.server = None

    def restart(self):
        self.stop()
        self.start()

    def _send(self, envelope):
        if self.hold_loads:
            self.envelopes.append(envelope)
        else:
            self.local_send(envelope)

    def _receipt(self, receipt):
        if self.hold_receipts:
            self.receipts.append(receipt)
        else:
            self.app.acknowledge(receipt)

    def call(self, path, body=None, status=200):
        actual, value = http_request(self.base, path, body)
        self.assertEqual(actual, status, value)
        return value

    def artwork(self, pixels=ART, art_id='orbit'):
        return self.call('/artwork', {'art_id': art_id, 'pixels': pixels})['revision_id']

    def sheet(self, revision_id=None):
        if revision_id is None:
            revision_id = self.artwork()
        return self.call('/sheets', {'revision_id': revision_id, 'left': LEFT, 'right': RIGHT})

    def dispatch(self, position, frame_id, request_id, session_id=SESSION, status=200):
        return self.call('/dispatches', {
            'session_id': session_id, 'position': position,
            'frame_id': frame_id, 'request_id': request_id,
        }, status)

    def order(self, dispatch_id):
        return self.call(f'/dispatches/{dispatch_id}')

    def load(self, envelope, screen_id=None, status=200):
        data = asdict(envelope) if not isinstance(envelope, dict) else envelope
        target = data['screen_id'] if screen_id is None else screen_id
        return self.call(f'/screens/{target}/loads', data, status)

    def pulse(self, number, status=200, session_id=SESSION):
        return self.call('/pulses', {'session_id': session_id, 'pulse': number}, status)

    def history(self, position=None):
        suffix = '' if position is None else f'?position={position}'
        return self.call(f'{SESSION_PATH}/shown{suffix}')

    def front(self, position='left'):
        return self.call(f'{SESSION_PATH}/screens/{position}')['front']

    def counts(self, *tables):
        with closing(self.app.connect()) as db:
            return tuple(db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in tables)
