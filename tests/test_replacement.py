from dataclasses import asdict

from samples.replacement_setup import prepare
from tests.fixture import SESSION, SESSION_PATH, WallTestCase

SPARE = 'panel-spare'


class ReplacementTests(WallTestCase):
    def replacement(self, activation_pulse, request_id='replace-left', position='left',
                    screen_id=SPARE, session_id=SESSION, status=200):
        return self.call('/screen-replacements', {
            'session_id': session_id, 'position': position,
            'replacement_screen_id': screen_id, 'activation_pulse': activation_pulse,
            'request_id': request_id,
        }, status)

    def layout(self, session_id=SESSION):
        return self.call(f'/sessions/{session_id}')

    def left_screen(self):
        return self.call(f'{SESSION_PATH}/screens/left')

    def scene(self):
        scene = prepare(self)
        scene['ids'] = {label: scene['orders'][label]['dispatch_id'] for label in 'ABC'}
        return scene

    def test_q1_registration_replay_and_lookup(self):
        self.pulse(9)
        record = self.replacement(10)
        self.assertEqual(record, {
            'replacement_id': record['replacement_id'],
            'session_id': SESSION, 'position': 'left', 'replacement_screen_id': SPARE,
            'activation_pulse': 10, 'request_id': 'replace-left',
            'status': 'pending', 'activated_pulse': None,
        })
        self.assertGreater(record['replacement_id'], 0)
        self.assertEqual(self.replacement(10), record)
        self.assertEqual(self.call(f"/screen-replacements/{record['replacement_id']}"), record)
        self.call('/screen-replacements/999', status=404)
        self.assertEqual(self.counts('screen_replacements'), (1,))

    def test_q1_rejects_bad_parameters(self):
        self.pulse(9)
        base = {'session_id': SESSION, 'position': 'left',
                'replacement_screen_id': SPARE, 'activation_pulse': 10,
                'request_id': 'replace-left'}
        for body in ({}, {**base, 'session_id': ''}, {**base, 'position': 3},
                     {**base, 'replacement_screen_id': None}, {**base, 'request_id': ''},
                     {**base, 'activation_pulse': -1}, {**base, 'activation_pulse': True},
                     {**base, 'activation_pulse': '10'}):
            with self.subTest(body=body):
                self.call('/screen-replacements', body, 400)
        self.assertEqual(self.counts('screen_replacements'), (0,))

    def test_q1_conflicts_keep_single_plan(self):
        self.pulse(9)
        record = self.replacement(10)
        self.replacement(10, request_id='replace-left', screen_id='panel-X', status=409)
        self.replacement(11, request_id='replace-left', status=409)
        self.replacement(10, request_id='other', status=409)
        self.replacement(10, request_id='replace-right', position='right', status=409)
        self.replacement(10, request_id='used', screen_id='panel-R', status=409)
        self.replacement(9, request_id='past', screen_id='panel-X', status=409)
        self.replacement(10, request_id='ghost', session_id='unknown', status=404)
        self.replacement(10, request_id='roof', position='roof', status=404)
        self.assertEqual(self.call(f"/screen-replacements/{record['replacement_id']}"), record)
        self.assertEqual(self.counts('screen_replacements'), (1,))

    def test_q2_plan_must_follow_processed_pulse(self):
        self.pulse(9)
        self.replacement(0, status=409)
        self.replacement(9, status=409)
        record = self.replacement(10)
        self.pulse(10)
        self.replacement(11, request_id='second', screen_id='panel-X', status=409)
        self.assertEqual(self.replacement(10)['replacement_id'], record['replacement_id'])

    def test_q3_activation_hands_over_slots(self):
        scene = self.scene()
        ids = scene['ids']
        self.assertEqual(self.layout()['placements'][0]['screen_id'], 'panel-L')
        record = self.replacement(10)
        self.assertEqual(self.left_screen()['screen_id'], 'panel-L')
        activation = self.pulse(10)
        self.assertEqual([(row['position'], row['screen_id'], row['frame_id'])
                          for row in activation['screens']],
                         [('left', SPARE, scene['frames']['B']),
                          ('right', 'panel-R', None)])
        self.assertEqual([(row['pulse'], row['position'], row['screen_id'], row['dispatch_id'])
                          for row in activation['shown']],
                         [(10, 'left', SPARE, ids['B'])])
        active = self.call(f"/screen-replacements/{record['replacement_id']}")
        self.assertEqual((active['status'], active['activated_pulse']), ('active', 10))
        self.assertEqual(self.layout()['placements'][0]['screen_id'], SPARE)
        self.assertEqual(self.left_screen()['screen_id'], SPARE)
        self.assertEqual(self.front()['frame_id'], scene['frames']['B'])
        self.assertEqual(self.front()['pixels'], [[[82, 0, 0]], [[0, 82, 0]]])
        self.assertEqual(self.order(ids['A'])['screen_id'], 'panel-L')

    def test_q3_late_former_receipt_keeps_slots(self):
        scene = self.scene()
        ids = scene['ids']
        self.replacement(10)
        self.pulse(10)
        self.load(scene['load_c'], 'panel-L', 409)
        replay = self.dispatch('left', scene['frames']['C'], 'swap-c')
        self.assertEqual(replay['dispatch_id'], ids['C'])
        self.assertEqual(self.order(ids['C'])['status'], 'pending')
        former_b = self.app.request('POST', '/screens/panel-L/loads', asdict(scene['load_b']))[0]
        self.assertEqual(former_b, 200)
        self.assertTrue(self.app.acknowledge(scene['receipt_b']))
        self.assertEqual(self.order(ids['B'])['status'], 'confirmed')
        self.assertEqual(self.front()['frame_id'], scene['frames']['B'])
        sent = self.envelopes.pop()
        self.assertEqual(sent.screen_id, SPARE)
        self.assertEqual(sent.dispatch_id, ids['C'])
        self.load(sent)
        self.app.acknowledge(self.receipts.pop())
        self.assertEqual(self.order(ids['C'])['status'], 'confirmed')

    def test_q4_c_arrives_before_activation(self):
        scene = self.scene()
        ids = scene['ids']
        self.load(scene['load_c'])
        self.replacement(10)
        result = self.pulse(10)
        self.assertEqual([(row['screen_id'], row['dispatch_id']) for row in result['shown']],
                         [(SPARE, ids['C'])])
        former_receipt = {'dispatch_id': ids['C'], 'session_id': SESSION,
                          'screen_id': 'panel-L', 'frame_id': scene['frames']['C'],
                          'revision_id': self._revision(ids['C'])}
        self.assertEqual(self.load(scene['load_c'], 'panel-L'), former_receipt)
        self.assertEqual(self.front()['frame_id'], scene['frames']['C'])

    def _revision(self, dispatch_id):
        with self.app.connect() as db:
            row = db.execute('''
                SELECT s.revision_id FROM frames AS f JOIN sheets AS s USING (sheet_id)
                WHERE f.frame_id = ?
            ''', (self.order(dispatch_id)['frame_id'],)).fetchone()
        return row['revision_id']

    def test_q5_empty_standby_skips_forward(self):
        art = self.artwork([[[7, 0, 0], [0, 0, 0]], [[0, 7, 0], [0, 0, 0]]], 'solo')
        frame = self.sheet(art)['left_frame_id']
        order = self.dispatch('left', frame, 'solo-left')
        self.pulse(9)
        record = self.replacement(12)
        result = self.pulse(12)
        self.assertEqual([(row['pulse'], row['screen_id'], row['dispatch_id'])
                          for row in self.history()],
                         [(9, 'panel-L', order['dispatch_id']),
                          (12, SPARE, order['dispatch_id'])])
        self.assertEqual([(row['screen_id'], row['frame_id']) for row in result['screens']],
                         [(SPARE, frame), ('panel-R', None)])
        self.pulse(11, status=409)
        active = self.call(f"/screen-replacements/{record['replacement_id']}")
        self.assertEqual((active['status'], active['activated_pulse']), ('active', 12))
        self.assertEqual(self.front()['frame_id'], frame)
        idle = self.pulse(13)
        self.assertEqual(idle['shown'], [])

    def test_q6_restart_keeps_replacement_records(self):
        scene = self.scene()
        ids = scene['ids']
        record = self.replacement(10)
        self.pulse(10)
        self.load(scene['load_c'], 'panel-L', 409)
        self.dispatch('left', scene['frames']['C'], 'swap-c')
        self.load(self.envelopes.pop())
        self.app.acknowledge(self.receipts.pop())
        self.app.acknowledge(scene['receipt_b'])
        self.pulse(11)
        self.restart()
        self.assertEqual(self.call(f"/screen-replacements/{record['replacement_id']}"),
                         {**record, 'status': 'active', 'activated_pulse': 10})
        self.assertEqual(self.order(ids['A'])['screen_id'], 'panel-L')
        self.assertEqual(self.order(ids['C'])['status'], 'confirmed')
        rows = self.history('left')
        self.assertEqual([(row['pulse'], row['screen_id'], row['dispatch_id']) for row in rows],
                         [(9, 'panel-L', ids['A']),
                          (10, SPARE, ids['B']),
                          (11, SPARE, ids['C'])])
        self.assertEqual(rows[0]['source'], {
            'art_id': 'replacement-A', 'revision_id': rows[0]['revision_id'],
            'sheet_id': rows[0]['source']['sheet_id'], 'side': 'left',
            'viewport': [0, 0, 1, 2],
        })
        self.assertEqual(self.layout()['placements'][0]['screen_id'], SPARE)
        self.assertEqual(self.front()['pixels'], [[[143, 0, 0]], [[0, 143, 0]]])
        self.assertEqual(self.pulse(11)['shown'][0]['screen_id'], SPARE)

    def test_q7_other_screens_advance_normally(self):
        scene = self.scene()
        self.hold_loads = False
        self.hold_receipts = False
        right = self.sheet(self.artwork([[[90, 91, 92], [93, 94, 95]],
                                           [[96, 97, 98], [99, 100, 101]]], 'neighbor'))
        order = self.dispatch('right', right['right_frame_id'], 'neighbor-right')
        self.replacement(10)
        result = self.pulse(10)
        self.assertEqual([(row['position'], row['screen_id'], row['dispatch_id'])
                          for row in result['shown']],
                         [('left', SPARE, scene['ids']['B']),
                          ('right', 'panel-R', order['dispatch_id'])])
        idle = self.pulse(11)
        self.assertEqual([(row['position'], row['screen_id']) for row in idle['screens']],
                         [('left', SPARE), ('right', 'panel-R')])
        self.assertEqual(idle['shown'], [])

    def test_q8_processed_pulse_replays_original_result(self):
        scene = self.scene()
        self.replacement(10)
        first = self.pulse(10)
        self.restart()
        self.assertEqual(self.pulse(10), first)
        self.assertEqual(self.pulse(9), scene['before'])
        self.assertEqual(self.counts('pulses', 'shown'), (2, 2))
        self.assertEqual(self.front()['frame_id'], scene['frames']['B'])

    def test_q9_new_dispatches_follow_current_screen(self):
        self.scene()
        self.replacement(10)
        self.pulse(10)
        art = self.artwork([[[61, 62, 63], [64, 65, 66]],
                            [[67, 68, 69], [70, 71, 72]]], 'later')
        frame = self.sheet(art)['left_frame_id']
        order = self.dispatch('left', frame, 'after-replacement')
        self.assertEqual(order['screen_id'], SPARE)
        envelope = self.envelopes.pop()
        self.assertEqual((envelope.screen_id, envelope.dispatch_id),
                         (SPARE, order['dispatch_id']))
        self.load(envelope)
        self.assertEqual([(row['screen_id'], row['dispatch_id'])
                          for row in self.pulse(11)['shown']],
                         [(SPARE, order['dispatch_id'])])

    def test_q10_former_entry_rejects_uninstalled_old_load(self):
        scene = self.scene()
        ids = scene['ids']
        self.replacement(10)
        self.pulse(10)
        self.load(scene['load_c'], 'panel-L', 409)
        self.assertEqual(self.counts('load_receipts'), (2,))
        self.assertEqual(self.order(ids['C'])['status'], 'pending')
        self.assertEqual(self.front()['frame_id'], scene['frames']['B'])
        self.assertEqual(self.pulse(11)['shown'], [])
        self.assertEqual(self.front()['frame_id'], scene['frames']['B'])
