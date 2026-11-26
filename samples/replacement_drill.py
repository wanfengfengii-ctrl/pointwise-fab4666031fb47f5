"""Run the single-screen replacement drill over the real HTTP entry points."""
import json
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from desk.server import build_application, serve

SESSION = 'gallery-day'
SESSION_PATH = f'/sessions/{SESSION}'
SPARE = 'panel-spare'
LEFT = [0, 0, 1, 2]
RIGHT = [1, 0, 2, 2]


def _pixels(value):
    return [[[value, 0, 0], [0, 0, 0]], [[0, value, 0], [0, 0, 0]]]


class Service:
    """A real HTTP service that can be stopped and started again on the same database."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.holder = {'envelopes': [], 'receipts': [], 'hold_loads': False,
                       'hold_receipts': False, 'sent': []}
        self.server = None
        self.thread = None
        self.base = None
        self.app = None
        self.local_send = None
        self.start()

    def _deliver(self, envelope):
        self.holder['sent'].append((envelope.dispatch_id, envelope.screen_id))
        if self.holder['hold_loads']:
            self.holder['envelopes'].append(envelope)
        else:
            self.local_send(envelope)

    def _receipt(self, receipt):
        if self.holder['hold_receipts']:
            self.holder['receipts'].append(receipt)
        else:
            self.app.acknowledge(receipt)

    def start(self):
        self.app = build_application(self.db_path, send_receipt=self._receipt)
        self.local_send = self.app.send_load
        self.app.send_load = self._deliver
        self.server = serve(self.app, 0)
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.thread = Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.01})
        self.thread.start()
        return self

    def stop(self):
        if self.server is not None:
            self.server.shutdown()
            self.thread.join()
            self.server.server_close()
            self.server = self.thread = self.base = self.app = None

    def restart(self):
        self.stop()
        return self.start()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.stop()


def call(base, method, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    request = Request(base + path, data=data, method=method,
                      headers={'Content-Type': 'application/json'})
    try:
        response = urlopen(request, timeout=5)
    except HTTPError as error:
        response = error
    with response:
        return response.code, json.load(response)


def expect(base, method, path, body=None, status=200):
    actual, value = call(base, method, path, body)
    assert actual == status, (path, actual, value)
    return value


def compose(base, label):
    revision = expect(base, 'POST', '/artwork', {
        'art_id': f'replacement-{label}',
        'pixels': _pixels({'A': 21, 'B': 82, 'C': 143}[label]),
    })
    sheet = expect(base, 'POST', '/sheets', {
        'revision_id': revision['revision_id'], 'left': LEFT, 'right': RIGHT,
    })
    return sheet['left_frame_id']


def dispatch(base, frame_id, request_id, position='left'):
    return expect(base, 'POST', '/dispatches', {
        'session_id': SESSION, 'position': position,
        'frame_id': frame_id, 'request_id': request_id,
    })


def pulse(base, number):
    return expect(base, 'POST', '/pulses', {'session_id': SESSION, 'pulse': number})


def register(base, request_id='replace-left', activation_pulse=10, status=200):
    return expect(base, 'POST', '/screen-replacements', {
        'session_id': SESSION, 'position': 'left', 'replacement_screen_id': SPARE,
        'activation_pulse': activation_pulse, 'request_id': request_id,
    }, status=status)


def boundary_case(db_path):
    """A/B/C around the planned pulse, then re-check everything after a restart."""
    with Service(db_path) as service:
        base = service.base
        frames = {label: compose(base, label) for label in 'ABC'}
        order_a = dispatch(base, frames['A'], 'swap-a')
        before = pulse(base, 9)
        assert [(row['pulse'], row['screen_id'], row['dispatch_id'])
                for row in before['shown']] == [(9, 'panel-L', order_a['dispatch_id'])]
        expect(base, 'GET', f'{SESSION_PATH}/screens/left')

        service.holder['hold_loads'] = True
        service.holder['hold_receipts'] = True
        order_b = dispatch(base, frames['B'], 'swap-b')
        load_b = service.holder['envelopes'].pop()
        expect(base, 'POST', '/screens/panel-L/loads', asdict(load_b))
        receipt_b = service.holder['receipts'].pop()
        order_c = dispatch(base, frames['C'], 'swap-c')
        load_c = service.holder['envelopes'].pop()

        replacement = register(base)
        before_screen = expect(base, 'GET', f'{SESSION_PATH}/screens/left')
        assert (before_screen['screen_id'], before_screen['front']['dispatch_id']) == (
            'panel-L', order_a['dispatch_id'])

        activation = pulse(base, 10)
        assert [(row['position'], row['screen_id'], row['frame_id'])
                for row in activation['screens']] == [
            ('left', SPARE, frames['B']), ('right', 'panel-R', None)]
        assert [(row['pulse'], row['screen_id'], row['dispatch_id'])
                for row in activation['shown']] == [(10, SPARE, order_b['dispatch_id'])]

        old_c_status = call(base, 'POST', '/screens/panel-L/loads', asdict(load_c))[0]
        assert old_c_status == 409
        after_screen = expect(base, 'GET', f'{SESSION_PATH}/screens/left')
        assert (after_screen['screen_id'], after_screen['front']['frame_id']) == (
            SPARE, frames['B'])

        replay_c = dispatch(base, frames['C'], 'swap-c')
        assert replay_c['dispatch_id'] == order_c['dispatch_id']
        sent_c = service.holder['envelopes'].pop()
        assert (sent_c.screen_id, sent_c.dispatch_id) == (SPARE, order_c['dispatch_id'])
        expect(base, 'POST', f'/screens/{sent_c.screen_id}/loads', asdict(sent_c))
        receipt_c = service.holder['receipts'].pop()
        assert service.app.acknowledge(receipt_c)
        assert service.app.acknowledge(receipt_b)
        after_b = expect(base, 'GET', f'{SESSION_PATH}/screens/left')
        assert after_b['front']['frame_id'] == frames['B']

        after = pulse(base, 11)
        assert [(row['pulse'], row['screen_id'], row['dispatch_id'])
                for row in after['shown']] == [(11, SPARE, order_c['dispatch_id'])]
        statuses = {
            label: expect(base, 'GET', f"/dispatches/{order['dispatch_id']}")['status']
            for label, order in (('A', order_a), ('B', order_b), ('C', order_c))
        }
        assert statuses == {'A': 'confirmed', 'B': 'confirmed', 'C': 'confirmed'}

        service.holder['hold_loads'] = False
        service.holder['hold_receipts'] = False
        service.restart()
        base = service.base
        kept = expect(base, 'GET', f"/screen-replacements/{replacement['replacement_id']}")
        assert (kept['status'], kept['activated_pulse']) == ('active', 10)
        old_a = expect(base, 'GET', f"/dispatches/{order_a['dispatch_id']}")
        assert old_a['screen_id'] == 'panel-L'
        layout = expect(base, 'GET', SESSION_PATH)
        assert layout['placements'][0]['screen_id'] == SPARE
        shown = expect(base, 'GET', f'{SESSION_PATH}/shown?position=left')
        rows = [(row['pulse'], row['screen_id'], row['dispatch_id']) for row in shown]
        assert rows == [(9, 'panel-L', order_a['dispatch_id']),
                        (10, SPARE, order_b['dispatch_id']),
                        (11, SPARE, order_c['dispatch_id'])]
        assert shown[0]['source']['revision_id'] == shown[0]['revision_id']
        front = expect(base, 'GET', f'{SESSION_PATH}/screens/left')
        assert front['front']['pixels'] == [[[143, 0, 0]], [[0, 143, 0]]]
        assert pulse(base, 9) == before
        assert pulse(base, 10) == activation
        return {
            'case_id': 'replacement-boundary',
            'input': {'frames': frames, 'planned_pulse': 10, 'spare': SPARE},
            'expected': {
                'pulse9': ['panel-L', order_a['dispatch_id']],
                'old_c_status': 409,
                'pulse10': ['panel-spare', order_b['dispatch_id']],
                'pulse11': ['panel-spare', order_c['dispatch_id']],
                'replacement_after_restart': ['active', 10],
                'original_dispatch_screen': 'panel-L',
            },
            'actual': {
                'pulse9': ['panel-L', order_a['dispatch_id']],
                'old_c_status': old_c_status,
                'pulse10': [activation['shown'][0]['screen_id'],
                            activation['shown'][0]['dispatch_id']],
                'pulse11': [after['shown'][0]['screen_id'], after['shown'][0]['dispatch_id']],
                'replacement_after_restart': [kept['status'], kept['activated_pulse']],
                'original_dispatch_screen': old_a['screen_id'],
            },
            'deliveries': {
                'before_boundary': {'pulse': 9, 'entry': 'panel-L',
                                    'dispatch': order_a['dispatch_id'],
                                    'sent_before_activation': [order_a['dispatch_id'],
                                                               order_b['dispatch_id']]},
                'after_boundary': {'pulse': 10, 'entry': SPARE,
                                   'dispatch': order_b['dispatch_id'],
                                   'resent_after_activation': [
                                       {'dispatch': sent_c.dispatch_id,
                                        'entry': sent_c.screen_id}]},
                'in_transit_c': {'original_entry_status': old_c_status,
                                 'original_dispatch': order_c['dispatch_id'],
                                 'resent_to': sent_c.screen_id,
                                 'pulse': 11},
                'visible_front_by_pulse': {
                    'pulse10': [after_screen['screen_id'], after_screen['front']['frame_id']],
                    'pulse11': [after['shown'][0]['screen_id'],
                                after['shown'][0]['frame_id']],
                },
            },
            'oracle': ('手算 A=21、B=82、C=143 三幅单列图；计划拍 10 的同一次提交内乙承接甲的'
                       '前画 A 与备画 B，按备画推进显示 B；C 的旧入口 409，按原单续送乙后第 11 拍'
                       '显示 C；重开服务后换机、原单、实显与出处照旧。'),
        }


def skip_case(db_path):
    """An empty standby skips from pulse 9 straight to pulse 12."""
    with Service(db_path) as service:
        base = service.base
        frame = compose(base, 'A')
        order = dispatch(base, frame, 'solo-left')
        pulse(base, 9)
        replacement = register(base, request_id='skip-left', activation_pulse=12)
        skipped = pulse(base, 12)
        assert [(row['screen_id'], row['frame_id']) for row in skipped['screens']] == [
            (SPARE, frame), ('panel-R', None)]
        shown = expect(base, 'GET', f'{SESSION_PATH}/shown?position=left')
        rows = [(row['pulse'], row['screen_id'], row['dispatch_id']) for row in shown]
        assert rows == [(9, 'panel-L', order['dispatch_id']),
                        (12, SPARE, order['dispatch_id'])]
        active = expect(base, 'GET', f"/screen-replacements/{replacement['replacement_id']}")
        assert (active['status'], active['activated_pulse']) == ('active', 12)
        return {
            'case_id': 'replacement-skip',
            'input': {'planned_pulse': 12, 'spare': SPARE, 'pulses_before': 9},
            'expected': {'activation': 12, 'pulse12': [SPARE, frame]},
            'actual': {'activation': active['activated_pulse'],
                       'pulse12': [skipped['shown'][0]['screen_id'],
                                   skipped['shown'][0]['frame_id']]},
            'oracle': '空备时从第 9 拍直接跳到第 12 拍，实际启用拍是 12，乙在第 12 拍显示沿用的 A。',
        }


def early_case(db_path):
    """C reaches the former screen before activation and is inherited as the standby."""
    with Service(db_path) as service:
        base = service.base
        frames = {label: compose(base, label) for label in 'AC'}
        dispatch(base, frames['A'], 'early-a')
        pulse(base, 9)
        service.holder['hold_loads'] = True
        service.holder['hold_receipts'] = True
        order_c = dispatch(base, frames['C'], 'early-c')
        load_c = service.holder['envelopes'].pop()
        receipt_c = expect(base, 'POST', '/screens/panel-L/loads', asdict(load_c))
        assert receipt_c['screen_id'] == 'panel-L'
        register(base, request_id='early-left', activation_pulse=10)
        activation = pulse(base, 10)
        assert [(row['screen_id'], row['dispatch_id']) for row in activation['shown']] == [
            (SPARE, order_c['dispatch_id'])]
        replay = expect(base, 'POST', '/screens/panel-L/loads', asdict(load_c))
        assert replay == receipt_c
        assert service.app.acknowledge(service.holder['receipts'][0])
        status = expect(base, 'GET', f"/dispatches/{order_c['dispatch_id']}")['status']
        assert status == 'confirmed'
        return {
            'case_id': 'replacement-early',
            'input': {'loaded_label': 'C', 'entry': 'panel-L', 'planned_pulse': 10},
            'expected': {'load_entry': 'panel-L',
                         'pulse10': [SPARE, order_c['dispatch_id']]},
            'actual': {'load_entry': receipt_c['screen_id'],
                       'pulse10': [activation['shown'][0]['screen_id'],
                                   activation['shown'][0]['dispatch_id']]},
            'oracle': 'C 在启用拍前先装到甲，乙在启用拍显示承接的备画 C，原装载确认仍归甲。',
        }


def run_all():
    evidence = []
    with TemporaryDirectory() as directory:
        root = Path(directory)
        evidence.append(boundary_case(root / 'boundary.sqlite3'))
        evidence.append(skip_case(root / 'skip.sqlite3'))
        evidence.append(early_case(root / 'early.sqlite3'))
    for item in evidence:
        print('POINTWISE_SCENARIO ' + json.dumps(item, ensure_ascii=False, separators=(',', ':')))
    return evidence


def main():
    run_all()


if __name__ == '__main__':
    main()
