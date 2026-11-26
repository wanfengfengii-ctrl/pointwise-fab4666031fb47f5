from tests.fixture import ART, LEFT, RIGHT, WallTestCase


class PreparationTests(WallTestCase):
    def test_p1_column_crop(self):
        revision = self.artwork()
        sheet = self.sheet(revision)
        proof = self.call(f"/sheets/{sheet['sheet_id']}")
        self.assertEqual(proof['revision_id'], revision)
        self.assertEqual(proof['art_id'], 'orbit')
        for side, bounds, expected in (
            ('left', LEFT, [[[1, 2, 3]], [[7, 8, 9]]]),
            ('right', RIGHT, [[[4, 5, 6]], [[10, 11, 12]]]),
        ):
            with self.subTest(side=side):
                frame = proof[side]
                self.assertEqual((frame['width'], frame['height']), (1, 2))
                self.assertEqual(frame['viewport'], bounds)
                self.assertEqual(frame['pixels'], expected)
                self.assertEqual(frame['frame_id'], sheet[f'{side}_frame_id'])
        order = self.dispatch('left', sheet['left_frame_id'], 'verified-proof')
        result = self.pulse(1)
        self.assertEqual(result['shown'][0]['dispatch_id'], order['dispatch_id'])
        self.assertEqual(self.front()['pixels'], [[[1, 2, 3]], [[7, 8, 9]]])
        self.assertIsNone(self.front('right'))

    def test_p2_rejects_ragged_grid(self):
        self.call('/artwork', {'art_id': 'orbit', 'pixels': [ART[0], ART[1][:1]]}, 400)
        self.assertEqual(self.counts('art_revisions'), (0,))
        revision = self.artwork()
        self.assertEqual(self.counts('art_revisions'), (1,))
        sheet = self.sheet(revision)
        self.assertEqual(self.call(f"/sheets/{sheet['sheet_id']}")['revision_id'], revision)

    def test_p2_rgb_limits(self):
        for invalid in ([], [[]], [[[True, 0, 0]]], [[[0, 256, 0]]],
                        [[[-1, 0, 0]]], [[[0.0, 0, 0]]], [[[0, 0]]]):
            with self.subTest(pixels=invalid):
                self.call('/artwork', {'art_id': 'limits', 'pixels': invalid}, 400)
        self.assertEqual(self.counts('art_revisions'), (0,))
        revision = self.artwork([[[0, 255, 0]]], 'limits')
        self.assertEqual(self.call(f'/artwork/{revision}')['pixels'], [[[0, 255, 0]]])

    def test_p3_atomic_pair(self):
        revision = self.artwork()
        existing = self.sheet(revision)
        for right in ([1, 0, 3, 2], [1, 0, 1, 2], [True, 0, 2, 2], [1, -1, 2, 2], [1, 0, 2, 3]):
            with self.subTest(right=right):
                self.call('/sheets', {'revision_id': revision, 'left': LEFT, 'right': right}, 400)
                self.assertEqual(self.counts('sheets', 'frames'), (1, 2))
        self.assertEqual(self.call(f"/sheets/{existing['sheet_id']}")['left']['pixels'],
                         [[[1, 2, 3]], [[7, 8, 9]]])
        self.sheet(revision)
        self.assertEqual(self.counts('sheets', 'frames'), (2, 4))

    def test_p3_unknown_revision(self):
        self.call('/sheets', {'revision_id': 100, 'left': LEFT, 'right': RIGHT}, 404)
        self.call('/sheets/100', status=404)
        self.assertEqual(self.counts('sheets', 'frames'), (0, 0))
