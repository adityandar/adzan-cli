import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


class CLITests(unittest.TestCase):
    def test_configure_schedule_next(self):
        with TemporaryDirectory() as d:
            base = [sys.executable, '-m', 'adzan', '--config', d + '/config.json', '--data-dir', d + '/data']
            configured = subprocess.run(base + ['configure', '--latitude', '-6.2', '--longitude', '106.8', '--timezone', 'Asia/Jakarta', '--location', 'Jakarta'], capture_output=True, text=True)
            self.assertEqual(configured.returncode, 0, configured.stderr)
            schedule = subprocess.run(base + ['schedule', '--date', '2026-09-08', '--offline', '--json'], capture_output=True, text=True)
            self.assertEqual(schedule.returncode, 0, schedule.stderr)
            result = json.loads(schedule.stdout)
            self.assertEqual(result['source'], 'lokal')
            self.assertEqual(len(result['prayers']), 5)
            nxt = subprocess.run(base + ['next', '--offline', '--json'], capture_output=True, text=True)
            self.assertEqual(nxt.returncode, 0, nxt.stderr)
            self.assertGreaterEqual(json.loads(nxt.stdout)['remaining_seconds'], 0)

    def test_missing_config_actionable_error(self):
        result = subprocess.run([sys.executable, '-m', 'adzan', '--config', '/tmp/adzan-nonexistent-config-test.json', 'schedule'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('configure', result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_new_config_uses_bundled_audio(self):
        with TemporaryDirectory() as d:
            config = Path(d) / 'config.json'
            result = subprocess.run([sys.executable, '-m', 'adzan', '--config', str(config),
                                     'configure', '--latitude', '-6.2', '--longitude', '106.8',
                                     '--timezone', 'Asia/Jakarta'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            values = json.loads(config.read_text())
            self.assertEqual(Path(values['audio']).name, 'adhan.mp3')
            self.assertEqual(Path(values['fajr_audio']).name, 'adhan-fajr.mp3')
            self.assertTrue(Path(values['audio']).is_file())
            self.assertTrue(Path(values['fajr_audio']).is_file())

    def test_audio_commands_select_regular_and_fajr(self):
        from unittest.mock import patch
        from adzan.cli import main
        from adzan.config import Config
        with TemporaryDirectory() as d:
            config = Path(d) / 'config.json'
            Config(audio='/tmp/regular.mp3', fajr_audio='/tmp/fajr.mp3').save(config)
            for flags, prayer in [([], 'Dhuhr'), (['--fajr'], 'Fajr')]:
                with self.subTest(flags=flags), patch('adzan.cli.check_audio'), patch('adzan.cli.play', return_value=True) as player:
                    self.assertEqual(main(['--config', str(config), 'test-audio'] + flags), 0)
                    self.assertEqual(player.call_args.args[1], prayer)

    def test_audio_failure_returns_nonzero(self):
        from unittest.mock import patch
        from adzan.cli import main
        from adzan.config import Config
        with TemporaryDirectory() as d:
            config = Path(d) / 'config.json'
            Config().save(config)
            with patch('adzan.cli.check_audio'), patch('adzan.cli.play', return_value=False):
                self.assertEqual(main(['--config', str(config), 'test-audio']), 1)
