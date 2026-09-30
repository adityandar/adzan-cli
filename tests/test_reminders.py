import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch
from adzan.config import Config
from adzan.cli import main
from adzan import daemon


class ReminderTests(unittest.TestCase):
    def test_defaults_and_old_config(self):
        with TemporaryDirectory() as d:
            path = Path(d) / 'config.json'
            path.write_text('{}')
            self.assertEqual(Config.load(path).reminder_minutes, 0)

    def test_validation(self):
        for minutes in (-1, 1440, 1.5, True):
            with self.subTest(minutes=minutes), self.assertRaises(ValueError):
                Config(reminder_minutes=minutes, reminder_audio='/tmp/reminder.mp3')
        with self.assertRaises(ValueError):
            Config(reminder_minutes=10)
        self.assertEqual(Config(reminder_minutes=10, reminder_audio='/tmp/r.mp3').reminder_minutes, 10)

    def test_midnight_and_stale_reminder(self):
        c = Config(reminder_minutes=10, reminder_audio='/tmp/r.mp3')
        target = datetime(2026, 10, 1, 0, 5, tzinfo=c.tz)
        events = daemon.reminder_events({'Fajr': target}, target - timedelta(minutes=10), c)
        self.assertEqual(events, [('Fajr', target - timedelta(minutes=10))])
        self.assertEqual(daemon.reminder_events({'Fajr': target}, target, c), [])
        self.assertEqual(daemon.reminder_events({'Fajr': target}, target - timedelta(minutes=8), c), [])
        self.assertEqual(daemon.reminder_events({'Fajr': target}, target - timedelta(minutes=10), Config()), [])

    def test_player_selects_reminder(self):
        c = Config(reminder_minutes=10, reminder_audio='/tmp/r.mp3')
        self.assertEqual(daemon.player_command(c, 'Reminder')[-1], '/tmp/r.mp3')

    def test_configure_missing_audio_does_not_save(self):
        with TemporaryDirectory() as d, redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            path = Path(d) / 'config.json'
            Config().save(path)
            original = path.read_text()
            self.assertEqual(main(['--config', str(path), 'configure', '--reminder-minutes', '10']), 2)
            self.assertEqual(path.read_text(), original)

    def test_configure_enable_test_and_disable(self):
        with TemporaryDirectory() as d, redirect_stdout(io.StringIO()):
            path, audio = Path(d) / 'config.json', Path(d) / 'r.mp3'
            audio.write_bytes(b'audio test fixture')
            Config(audio=str(audio)).save(path)
            base = ['--config', str(path)]
            self.assertEqual(main(base + ['configure', '--reminder-minutes', '10', '--reminder-audio', str(audio)]), 0)
            with patch('adzan.cli.check_audio'), patch('adzan.cli.play', return_value=True) as player:
                self.assertEqual(main(base + ['test-audio', '--reminder']), 0)
                self.assertEqual(player.call_args.args[1], 'Reminder')
            self.assertEqual(main(base + ['configure', '--reminder-minutes', '0']), 0)
            self.assertEqual(Config.load(path).reminder_minutes, 0)

    def test_reminder_claim_separate_from_adhan(self):
        with TemporaryDirectory() as d:
            ledger = daemon.Ledger(Path(d) / 'events.db')
            self.assertTrue(ledger.claim('2026-10-01:Fajr:reminder'))
            self.assertTrue(ledger.claim('2026-10-01:Fajr'))
            self.assertFalse(daemon.Ledger(Path(d) / 'events.db').claim('2026-10-01:Fajr:reminder'))

    def test_player_stops_reminder_at_adhan(self):
        import threading
        c = Config(reminder_minutes=1, reminder_audio='/tmp/r.mp3')
        cutoff = datetime.now(c.tz)
        process = MagicMock()
        process.poll.return_value = None
        with patch('adzan.daemon.subprocess.Popen', return_value=process), patch('adzan.daemon.time.time', return_value=cutoff.timestamp()):
            self.assertTrue(daemon.play(c, 'Reminder', threading.Event(), until=cutoff))
        process.terminate.assert_called_once()
        process.wait.assert_called_once_with(timeout=0.5)

    def test_daemon_plays_and_persists_reminder(self):
        import sqlite3
        c = Config(reminder_minutes=10, reminder_audio='/tmp/r.mp3')
        now = datetime.now(c.tz)
        target = now + timedelta(minutes=10, seconds=-1)
        provider = MagicMock(config=c)
        provider.get.side_effect = lambda day, online: ({'Fajr': target} if day == target.date() else {}, 'cache')
        def played(config, prayer, stop, until=None):
            self.assertEqual(prayer, 'Reminder')
            self.assertEqual(until, target)
            stop.set()
            return True
        with TemporaryDirectory() as d:
            with patch('adzan.daemon.check_audio'), patch('adzan.daemon.play', side_effect=played):
                daemon.run(provider, Path(d), offline=True)
            db = sqlite3.connect(Path(d) / 'events.sqlite3')
            try:
                self.assertEqual(db.execute('SELECT id, status FROM events').fetchall(),
                                 [(f'{target.date()}:Fajr:reminder', 'played')])
            finally:
                db.close()

    def test_missing_reminder_file_rejected_at_startup(self):
        with TemporaryDirectory() as d:
            audio = Path(d) / 'adzan.mp3'
            audio.write_bytes(b'test')
            c = Config(audio=str(audio), reminder_minutes=10, reminder_audio=str(Path(d) / 'missing.mp3'))
            with patch('adzan.daemon.shutil.which', return_value='/bin/mpv'), self.assertRaisesRegex(ValueError, '--reminder-audio'):
                daemon.check_audio(c)

    def test_reminder_does_not_change_schedule_cache_key(self):
        self.assertEqual(Config().calculation_key(), Config(reminder_minutes=10, reminder_audio='/tmp/r.mp3').calculation_key())

    def test_disable_after_reminder_file_deleted(self):
        with TemporaryDirectory() as d, redirect_stdout(io.StringIO()):
            audio = Path(d) / 'adzan.mp3'
            audio.write_bytes(b'test')
            path = Path(d) / 'config.json'
            Config(audio=str(audio), reminder_minutes=10, reminder_audio=str(Path(d) / 'missing.mp3')).save(path)
            self.assertEqual(main(['--config', str(path), 'configure', '--reminder-minutes', '0']), 0)
            self.assertEqual(Config.load(path).reminder_minutes, 0)
