from copy import deepcopy
from dataclasses import asdict, replace

from tests.fixture import SESSION, WallTestCase


class PlayoutTests(WallTestCase):
    def setUp(self):
        super().setUp()
        self.sheet_a = self.sheet()
        self.sheet_b = self.sheet(self.artwork([[[51, 52, 53], [54, 55, 56]],
                                                 [[57, 58, 59], [60, 61, 62]]]))
        self.left_a = self.sheet_a['left_frame_id']
        self.left_b = self.sheet_b['left_frame_id']
        self.right_a = self.sheet_a['right_frame_id']
        self.right_b = self.sheet_b['right_frame_id']

    def test_s1_single_screen(self):
        self.dispatch('left', self.left_a, 'old-left')
        self.dispatch('right', self.right_a, 'old-right')
        self.pulse(9)
        order = self.dispatch('left', self.left_b, 'new-left')
        self.assertEqual(order['status'], 'confirmed')
        self.assertEqual(self.front()['frame_id'], self.left_a)
        result = self.pulse(10)
        self.assertEqual([row['frame_id'] for row in result['screens']], [self.left_b, self.right_a])
        self.assertEqual([(row['position'], row['frame_id']) for row in result['shown']],
                         [('left', self.left_b)])

    def test_s1_payload_integrity(self):
        original = self.dispatch('left', self.left_a, 'keep-left')
        self.hold_loads = True
        damaged = self.dispatch('left', self.left_b, 'tampered')
        payload = asdict(self.envelopes.pop())
        payload['pixels'] = deepcopy([[list(color) for color in row] for row in payload['pixels']])
        payload['pixels'][0][0][0] = 99
        self.load(payload, status=400)
        self.assertEqual(self.order(damaged['dispatch_id'])['status'], 'pending')
        self.assertEqual(self.counts('load_receipts'), (1,))
        result = self.pulse(1)
        self.assertEqual([row['dispatch_id'] for row in result['shown']], [original['dispatch_id']])
        self.assertEqual(self.front()['pixels'], [[[1, 2, 3]], [[7, 8, 9]]])

    def test_s1_consume_standby(self):
        self.dispatch('left', self.left_a, 'a')
        self.pulse(1)
        self.dispatch('left', self.left_b, 'b')
        self.assertEqual(self.pulse(2)['shown'][0]['frame_id'], self.left_b)
        idle = self.pulse(3)
        self.assertEqual(idle['screens'][0]['frame_id'], self.left_b)
        self.assertEqual(idle['shown'], [])
        self.assertEqual([row['frame_id'] for row in self.history()], [self.left_a, self.left_b])

    def test_s1_two_independent_screens(self):
        self.dispatch('right', self.right_b, 'right-from-b')
        self.dispatch('left', self.left_a, 'left-from-a')
        result = self.pulse(5)
        self.assertEqual([(row['position'], row['frame_id']) for row in result['shown']],
                         [('left', self.left_a), ('right', self.right_b)])
        self.assertEqual([(row['pulse'], row['position']) for row in self.history()],
                         [(5, 'left'), (5, 'right')])

    def test_s1_record_only_on_pulse(self):
        self.hold_loads = True
        order = self.dispatch('left', self.left_a, 'first')
        self.assertEqual(self.history(), [])
        self.assertIsNone(self.front())
        self.load(self.envelopes.pop())
        self.assertEqual(self.order(order['dispatch_id'])['status'], 'confirmed')
        self.assertEqual(self.history(), [])
        self.assertIsNone(self.front())
        self.pulse(6)
        self.assertEqual([(row['pulse'], row['dispatch_id']) for row in self.history()],
                         [(6, order['dispatch_id'])])
        self.hold_loads = False
        second = self.dispatch('left', self.left_a, 'same-picture-again')
        result = self.pulse(7)
        self.assertEqual([row['dispatch_id'] for row in result['shown']], [second['dispatch_id']])

    def test_s1_first_arrivals_and_replay(self):
        self.hold_loads = True
        first = self.dispatch('left', self.left_a, 'queued-first')
        self.dispatch('left', self.left_b, 'queued-second')
        left_a, left_b = self.envelopes
        received_b = self.load(left_b)
        self.load(left_a)
        self.assertEqual(self.load(left_b), received_b)
        self.assertEqual(self.pulse(1)['shown'][0]['dispatch_id'], first['dispatch_id'])
        self.assertEqual(self.front()['frame_id'], self.left_a)

    def test_s2_held_delivery(self):
        self.dispatch('left', self.left_a, 'establish-left')
        self.dispatch('right', self.right_a, 'establish-right')
        self.pulse(1)
        self.hold_loads = True
        order = self.dispatch('left', self.left_b, 'held')
        self.assertEqual(order['status'], 'pending')
        idle = self.pulse(2)
        self.assertEqual([row['frame_id'] for row in idle['screens']], [self.left_a, self.right_a])
        self.assertEqual(idle['shown'], [])
        self.assertEqual({row['pulse'] for row in self.history()}, {1})

    def test_s2_request_reuse(self):
        self.hold_loads = True
        original = self.dispatch('left', self.left_a, 'reused')
        self.assertEqual(self.dispatch('left', self.left_a, 'reused'), original)
        self.dispatch('left', self.left_b, 'reused', status=409)
        self.dispatch('right', self.left_a, 'reused', status=409)
        self.assertEqual(self.order(original['dispatch_id']), original)
        self.assertEqual(self.counts('dispatches'), (1,))
        self.assertEqual(len(self.envelopes), 2)
        self.assertEqual(self.envelopes[0], self.envelopes[1])
        self.load(self.envelopes[1])
        self.assertEqual(self.pulse(1)['shown'][0]['frame_id'], self.left_a)

    def test_s2_unknown_target(self):
        self.dispatch('left', self.left_a, 'new', session_id='unknown', status=404)
        self.dispatch('roof', self.left_a, 'new', status=404)
        self.dispatch('left', 999, 'new', status=404)
        self.call('/dispatches/999', status=404)
        self.pulse(1, status=404, session_id='unknown')
        self.assertEqual(self.counts('dispatches', 'pulses'), (0, 0))

    def test_s2_held_receipt(self):
        self.hold_loads = True
        self.hold_receipts = True
        order = self.dispatch('left', self.left_a, 'load-with-lost-reply')
        self.assertEqual(self.pulse(1)['shown'], [])
        first_reply = self.load(self.envelopes.pop())
        self.assertEqual(self.order(order['dispatch_id'])['status'], 'pending')
        forged = replace(self.receipts[0], frame_id=self.left_b)
        self.assertFalse(self.app.acknowledge(forged))
        self.assertEqual(self.order(order['dispatch_id'])['status'], 'pending')
        self.assertEqual(self.pulse(2)['shown'][0]['frame_id'], self.left_a)
        self.assertEqual(self.order(order['dispatch_id'])['status'], 'pending')
        self.restart()
        self.hold_loads = False
        self.hold_receipts = False
        replay = self.dispatch('left', self.left_a, 'load-with-lost-reply')
        self.assertEqual(replay['dispatch_id'], first_reply['dispatch_id'])
        self.assertEqual(replay['status'], 'confirmed')
        self.assertTrue(self.app.acknowledge(self.receipts.pop()))
        self.assertEqual(self.pulse(3)['shown'], [])
        self.assertEqual(len(self.history()), 1)

    def test_s3_wrong_screen(self):
        self.hold_loads = True
        order = self.dispatch('left', self.left_a, 'for-left')
        self.load(self.envelopes.pop(), 'panel-R', 409)
        self.assertEqual(self.order(order['dispatch_id'])['status'], 'pending')
        self.assertEqual([row['frame_id'] for row in self.pulse(1)['screens']], [None, None])

    def test_s3_preserve_standby(self):
        expected = self.dispatch('right', self.right_b, 'keep-right')
        self.hold_loads = True
        wrong = self.dispatch('left', self.left_a, 'wrong-target', session_id=SESSION)
        self.load(self.envelopes.pop(), 'panel-R', 409)
        self.assertEqual(self.order(wrong['dispatch_id'])['status'], 'pending')
        self.assertEqual(self.counts('load_receipts'), (1,))
        self.assertEqual([item['dispatch_id'] for item in self.pulse(1)['shown']],
                         [expected['dispatch_id']])
