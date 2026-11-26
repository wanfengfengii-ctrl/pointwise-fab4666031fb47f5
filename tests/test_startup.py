import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from desk.placements import PlacementStore
from desk.server import Application, build_application
from desk.session import SessionStore
from tests.fixture import SESSION, SESSION_PATH, WallTestCase
from wall.buffers import BufferStore


class RestartTests(WallTestCase):
    def test_s1_restart_preserves_setup(self):
        sheet = self.sheet()
        frame = sheet['left_frame_id']
        self.dispatch('left', frame, 'open')
        original = self.pulse(10)
        with closing(self.app.connect()) as db, db:
            db.execute('UPDATE sessions SET name = ? WHERE session_id = ?', ('周末特展', SESSION))
            db.execute('UPDATE placements SET name = ? WHERE session_id = ? AND position = ?',
                       ('西侧屏', SESSION, 'left'))
        for _ in range(2):
            self.restart()
            layout = self.call(SESSION_PATH)
            self.assertEqual(layout['name'], '周末特展')
            self.assertEqual(layout['placements'][0]['name'], '西侧屏')
            self.assertEqual(self.front()['frame_id'], frame)
            self.assertEqual(self.pulse(10), original)
            self.assertEqual(self.counts('sessions', 'placements', 'screen_buffers', 'pulses', 'shown'),
                             (1, 2, 2, 1, 1))


class InitializationTests(unittest.TestCase):
    def test_initialization_failure_rolls_back_and_retries(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'wall.sqlite3'
            model = Application(path, None, None)
            with closing(model.connect()) as db, db:
                SessionStore.install_schema(db)
                PlacementStore.install_schema(db)
                BufferStore.install_schema(db)
                db.execute('''
                    CREATE TRIGGER stop_second_screen BEFORE INSERT ON screen_buffers
                    WHEN NEW.screen_id = 'panel-R'
                    BEGIN SELECT RAISE(ABORT, 'second screen unavailable'); END
                ''')
            with self.assertRaisesRegex(sqlite3.IntegrityError, 'second screen unavailable'):
                build_application(path)
            with closing(model.connect()) as db, db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0], 0)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM placements').fetchone()[0], 0)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM screen_buffers').fetchone()[0], 0)
                self.assertIsNone(db.execute('''
                    SELECT name FROM sqlite_master WHERE name = 'initialization'
                ''').fetchone())
                db.execute('DROP TRIGGER stop_second_screen')
            app = build_application(path)
            self.assertEqual(app.request('GET', SESSION_PATH)[0], 200)
            with closing(app.connect()) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM screen_buffers').fetchone()[0], 2)
                self.assertEqual(db.execute('SELECT complete FROM initialization').fetchone()[0], 1)
