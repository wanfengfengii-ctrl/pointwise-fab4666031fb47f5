from tests.fixture import ART, SESSION_PATH, WallTestCase


class ShownHistoryTests(WallTestCase):
    def test_r1_original_source_after_restart(self):
        original = self.artwork()
        sheet = self.sheet(original)
        proof_path = f"/sheets/{sheet['sheet_id']}"
        self.dispatch('left', sheet['left_frame_id'], 'original')
        shown = self.pulse(10)
        new = self.artwork([[[199, 200, 201]]])
        self.assertNotEqual(original, new)
        self.restart()
        entry, = self.history()
        self.assertEqual(entry['pulse'], 10)
        self.assertEqual(entry['frame_id'], shown['shown'][0]['frame_id'])
        self.assertEqual(entry['revision_id'], original)
        self.assertEqual(entry['source'], {
            'art_id': 'orbit', 'revision_id': original, 'sheet_id': sheet['sheet_id'],
            'side': 'left', 'viewport': [0, 0, 1, 2],
        })
        self.assertEqual(self.call(proof_path)['left']['pixels'], [[[1, 2, 3]], [[7, 8, 9]]])
        self.assertEqual(self.call(f'/artwork/{original}')['pixels'], ART)
        self.assertEqual(self.front()['frame_id'], entry['frame_id'])
        self.assertEqual(self.front()['pixels'], [[[1, 2, 3]], [[7, 8, 9]]])

    def test_r1_history_filter(self):
        sheet = self.sheet()
        self.assertEqual(self.history(), [])
        self.dispatch('left', sheet['left_frame_id'], 'left-first')
        self.pulse(2)
        self.assertEqual(self.history('right'), [])
        self.dispatch('right', sheet['right_frame_id'], 'right-on-ten')
        self.dispatch('left', sheet['left_frame_id'], 'left-on-ten')
        self.pulse(10)
        self.restart()
        self.assertEqual([(row['pulse'], row['position']) for row in self.history()],
                         [(2, 'left'), (10, 'left'), (10, 'right')])
        right, = self.history('right')
        self.assertEqual(right['frame_id'], sheet['right_frame_id'])
        self.assertEqual(right['source']['viewport'], [1, 0, 2, 2])
        self.call(f'{SESSION_PATH}/shown?position=roof', status=404)
        self.call('/sessions/unknown/shown', status=404)

    def test_r2_replay(self):
        sheet = self.sheet()
        self.dispatch('left', sheet['left_frame_id'], 'left')
        original = self.pulse(4)
        self.assertEqual(self.pulse(4), original)
        self.assertEqual(len(self.history()), 1)
        self.assertEqual(self.counts('pulses', 'shown'), (1, 1))

    def test_r2_replay_after_later_pulse(self):
        sheet = self.sheet()
        a, b = sheet['left_frame_id'], sheet['right_frame_id']
        self.dispatch('left', a, 'a')
        first = self.pulse(10)
        self.dispatch('left', b, 'b')
        self.pulse(12)
        pending = self.dispatch('left', a, 'a-again')
        self.restart()
        self.assertEqual(self.pulse(10), first)
        self.assertEqual(self.front()['frame_id'], b)
        self.assertEqual([(row['pulse'], row['frame_id']) for row in self.history()], [(10, a), (12, b)])
        self.assertEqual(self.pulse(13)['shown'][0]['dispatch_id'], pending['dispatch_id'])

    def test_r2_unseen_old(self):
        sheet = self.sheet()
        self.dispatch('left', sheet['left_frame_id'], 'before-gap')
        self.pulse(10)
        self.pulse(12)
        pending = self.dispatch('left', sheet['right_frame_id'], 'after-gap')
        self.pulse(11, status=409)
        self.assertEqual(self.front()['frame_id'], sheet['left_frame_id'])
        self.assertEqual(self.counts('pulses', 'shown'), (2, 1))
        self.assertEqual(self.pulse(13)['shown'][0]['dispatch_id'], pending['dispatch_id'])
