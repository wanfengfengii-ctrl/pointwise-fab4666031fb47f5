from contextlib import closing

from desk.bootstrap import seed_session
from tests.fixture import SESSION_PATH, WallTestCase


class WorkdayTests(WallTestCase):
    def test_two_sessions_isolate_dispatches_slots_and_pulses(self):
        with closing(self.app.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            seed_session(db, {
                'session_id': 'evening', 'name': '夜场',
                'placements': [{'position': 'left', 'screen_id': 'panel-L', 'name': '左屏'}],
            })
        sheet = self.sheet()
        daytime = self.dispatch('left', sheet['left_frame_id'], 'open')
        evening = self.dispatch('left', sheet['right_frame_id'], 'open', session_id='evening')
        self.assertNotEqual(daytime['dispatch_id'], evening['dispatch_id'])
        self.assertEqual(self.pulse(10)['shown'][0]['dispatch_id'], daytime['dispatch_id'])
        self.assertIsNone(self.call('/sessions/evening/screens/left')['front'])
        self.assertEqual(self.call('/sessions/evening/shown'), [])
        self.assertEqual(self.pulse(1, session_id='evening')['shown'][0]['dispatch_id'], evening['dispatch_id'])
        self.assertEqual(self.front()['frame_id'], sheet['left_frame_id'])
        self.assertEqual(self.call('/sessions/evening/shown')[0]['frame_id'], sheet['right_frame_id'])

    def test_write_failure_rolls_back_both_screens_and_pulse(self):
        sheet = self.sheet()
        self.dispatch('left', sheet['left_frame_id'], 'opening-left')
        self.dispatch('right', sheet['right_frame_id'], 'opening-right')
        with closing(self.app.connect()) as db, db:
            db.execute('''
                CREATE TRIGGER stop_right_record BEFORE INSERT ON shown
                WHEN NEW.position = 'right'
                BEGIN SELECT RAISE(ABORT, 'recorder stopped'); END
            ''')
        self.pulse(10, status=500)
        self.assertEqual(self.call(f'{SESSION_PATH}/shown'), [])
        self.assertIsNone(self.front())
        self.assertIsNone(self.front('right'))
        self.assertEqual(self.counts('pulses', 'shown', 'load_receipts'), (0, 0, 2))
        with closing(self.app.connect()) as db, db:
            db.execute('DROP TRIGGER stop_right_record')
        retry = self.pulse(10)
        self.assertEqual([row['position'] for row in retry['shown']], ['left', 'right'])
        self.assertEqual(self.pulse(10), retry)
        self.assertEqual(self.counts('pulses', 'shown'), (1, 2))
