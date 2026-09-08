import gc
import sqlite3
import threading
import unittest
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch
from adzan.config import Config
from adzan.daemon import Ledger, play, run


class DaemonTests(unittest.TestCase):
    def test_ledger_closes_connections(self):
        with TemporaryDirectory() as d, warnings.catch_warnings(record=True) as recorded:
            warnings.simplefilter('always', ResourceWarning)
            ledger = Ledger(Path(d) / 'ledger.db')
            ledger.claim('day:Fajr')
            ledger.finish('day:Fajr', 'played')
            gc.collect()
            self.assertFalse([w for w in recorded if 'unclosed database' in str(w.message)])

    def test_stop_terminates_player(self):
        stop = threading.Event()
        stop.set()
        process = MagicMock()
        process.poll.return_value = None
        with patch('adzan.daemon.subprocess.Popen', return_value=process):
            self.assertFalse(play(Config(), 'Fajr', stop))
        process.terminate.assert_called_once()

    def test_daemon_records_playback(self):
        c = Config()
        now = datetime.now(c.tz)
        provider = MagicMock(config=c)
        provider.get.return_value = ({'Fajr': now - timedelta(seconds=1)}, 'cache')
        # All other dates return no events.
        provider.get.side_effect = lambda day, online: ({'Fajr': now - timedelta(seconds=1)} if day == now.date() else {}, 'cache')
        def played(config, prayer, stop):
            stop.set()
            return True
        with TemporaryDirectory() as d:
            root = Path(d)
            with patch('adzan.daemon.check_audio'), patch('adzan.daemon.play', side_effect=played):
                run(provider, root, offline=True)
            db = sqlite3.connect(root / 'events.sqlite3')
            try:
                self.assertEqual(db.execute('SELECT status FROM events').fetchall(), [('played',)])
            finally:
                db.close()
