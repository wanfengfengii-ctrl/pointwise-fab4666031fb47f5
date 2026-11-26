import json
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.request import Request, urlopen

from desk.server import build_application, serve

PIXELS = [[[255, 0, 0], [0, 255, 0]], [[0, 0, 255], [255, 255, 0]]]
SESSION = '/sessions/gallery-day'


@contextmanager
def running_service(db_path: Path):
    with serve(build_application(db_path), 0) as server:
        thread = Thread(target=server.serve_forever, kwargs={'poll_interval': 0.05})
        thread.start()
        try:
            yield f'http://127.0.0.1:{server.server_port}'
        finally:
            server.shutdown()
            thread.join()


def request(base: str, path: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    call = Request(base + path, data=data, headers={'Content-Type': 'application/json'})
    with urlopen(call, timeout=5) as response:
        return json.load(response)


def main() -> None:
    expected = {'left': [[[255, 0, 0]], [[0, 0, 255]]],
                'right': [[[0, 255, 0]], [[255, 255, 0]]]}
    with TemporaryDirectory() as directory:
        db_path = Path(directory) / 'gallery.sqlite3'
        with running_service(db_path) as base:
            placements = request(base, SESSION)['placements']
            assert [item['position'] for item in placements] == ['left', 'right']
            original = request(base, '/artwork', {'art_id': 'orbit', 'pixels': PIXELS})
            composition = {'revision_id': original['revision_id'], 'left': [0, 0, 1, 2], 'right': [1, 0, 2, 2]}
            sheet = request(base, '/sheets', composition)
            proof_path = f"/sheets/{sheet['sheet_id']}"
            proof = request(base, proof_path)
            crops = {side: proof[side]['pixels'] for side in ('left', 'right')}
            assert crops == expected
            for position, pulse in (('left', 10), ('right', 11)):
                order = request(base, '/dispatches', {
                    'session_id': 'gallery-day', 'position': position,
                    'frame_id': sheet[f'{position}_frame_id'], 'request_id': f'open-{position}',
                })
                assert order['status'] == 'confirmed'
                assert request(base, f'{SESSION}/screens/{position}')['front'] is None
                result = request(base, '/pulses', {'session_id': 'gallery-day', 'pulse': pulse})
                assert [(item['position'], item['frame_id']) for item in result['shown']] == [
                    (position, sheet[f'{position}_frame_id']),
                ]
                if pulse == 10:
                    assert result['screens'][1]['frame_id'] is None
            visible = {side: request(base, f'{SESSION}/screens/{side}')['front']['pixels']
                       for side in ('left', 'right')}
            assert visible == expected
            updated = request(base, '/artwork', {'art_id': 'orbit', 'pixels': [[[8, 8, 8]]]})
            assert updated['revision_id'] != original['revision_id']
        with running_service(db_path) as base:
            history = request(base, f'{SESSION}/shown')
            actual_shows = [[row['pulse'], row['position'], row['frame_id'], row['source']['revision_id']]
                            for row in history]
            expected_shows = [[10, 'left', sheet['left_frame_id'], original['revision_id']],
                              [11, 'right', sheet['right_frame_id'], original['revision_id']]]
            assert actual_shows == expected_shows
            assert request(base, proof_path) == proof
            assert request(base, f"/artwork/{original['revision_id']}")['pixels'] == PIXELS
    evidence = {
        'case_id': 'p1',
        'input': {'pixels': PIXELS, 'left': composition['left'], 'right': composition['right']},
        'expected': expected,
        'actual': crops,
        'downstream_expected': {'visible_pixels': expected, 'shows': expected_shows},
        'downstream_actual': {'visible_pixels': visible, 'shows': actual_shows},
        'code_paths': ['composition/render.py', 'composition/sheets.py', 'wall/ingress.py',
                       'wall/pulses.py', 'wall/http.py', 'records/history.py'],
        'oracle': '手算两列分别为红蓝、绿黄。按两次公开发拍的拍号、指定画面号和初次导入修订核对实显。',
    }
    print('POINTWISE_SCENARIO ' + json.dumps(evidence, ensure_ascii=False, separators=(',', ':')))


if __name__ == '__main__':
    main()
