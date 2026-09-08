import io
import json
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from adzan.cli import main

CITY = {'id': 1630789, 'name': 'Pontianak', 'latitude': -0.03194, 'longitude': 109.325,
        'timezone': 'Asia/Pontianak', 'admin1': 'Kalimantan Barat', 'country': 'Indonesia'}


class LocationTests(unittest.TestCase):
    def test_search_without_config(self):
        with patch('adzan.locations.request', return_value={'results': [CITY]}), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['locations', 'Pontianak', '--json']), 0)
        self.assertEqual(json.loads(output.getvalue())[0]['id'], CITY['id'])

    def test_configure_name_resolves_coordinates(self):
        with TemporaryDirectory() as d, patch('adzan.locations.request', return_value={'results': [CITY]}), redirect_stdout(io.StringIO()):
            path = Path(d) / 'config.json'
            self.assertEqual(main(['--config', str(path), 'configure', '--location', 'Pontianak']), 0)
            result = json.loads(path.read_text())
            self.assertEqual(result['latitude'], CITY['latitude'])
            self.assertEqual(result['timezone'], CITY['timezone'])

    def test_ambiguous_noninteractive_does_not_save(self):
        with TemporaryDirectory() as d, patch('adzan.locations.request', return_value={'results': [CITY, dict(CITY, id=2)]}), patch('sys.stdin.isatty', return_value=False), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as error:
            path = Path(d) / 'config.json'
            self.assertEqual(main(['--config', str(path), 'configure', '--location', 'Pontianak']), 2)
            self.assertFalse(path.exists())
            self.assertIn('--location-id', error.getvalue())

    def test_configure_by_id(self):
        with TemporaryDirectory() as d, patch('adzan.locations.request', return_value=CITY), redirect_stdout(io.StringIO()):
            path = Path(d) / 'config.json'
            self.assertEqual(main(['--config', str(path), 'configure', '--location-id', str(CITY['id'])]), 0)
            self.assertEqual(json.loads(path.read_text())['longitude'], CITY['longitude'])

    def test_no_results_preserves_config(self):
        with TemporaryDirectory() as d, patch('adzan.locations.request', return_value={}), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            path = Path(d) / 'config.json'
            self.assertEqual(main(['--config', str(path), 'configure', '--location', 'xyz']), 2)
            self.assertFalse(path.exists())
