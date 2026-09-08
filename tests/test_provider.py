import copy
import json
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from adzan.config import Config
from adzan.astronomy import calculate
from adzan.schedule import Provider


class CalendarTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.c = Config(latitude=-6.2, longitude=106.8, timezone='Asia/Jakarta')
        self.p = Provider(self.c, Path(self.tmp.name))
        self.payload = json.loads((Path(__file__).parent / 'fixtures/aladhan-jakarta-2026-09.json').read_text())

    def test_real_month_offline_difference_at_most_one_minute(self):
        days = self.p.parse_month(self.payload, 2026, 9)
        self.assertEqual(len(days), 30)
        for day, times in days.items():
            local = calculate(date.fromisoformat(day), self.c)
            for name, value in times.items():
                self.assertLessEqual(abs((local[name] - datetime.fromisoformat(value)).total_seconds()), 60, (day, name))

    def test_rejects_malformed_response(self):
        for value in (None, [], {'code': 200, 'data': [None]}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.p.parse_month(value, 2026, 9)

    def test_rejects_wrong_metadata(self):
        for key, value in [('timezone', 'UTC'), ('latitude', float('nan')), ('school', 'HANAFI')]:
            payload = copy.deepcopy(self.payload)
            payload['data'][0]['meta'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.p.parse_month(payload, 2026, 9)

    def test_rejects_partial_calendar(self):
        self.payload['data'].pop()
        with self.assertRaises(ValueError):
            self.p.parse_month(self.payload, 2026, 9)

    def test_failed_network_falls_back(self):
        with patch.object(self.p, 'fetch_month', side_effect=OSError('offline')):
            with self.assertLogs('adzan.schedule', level='WARNING'):
                times, source = self.p.get(date(2026, 9, 8))
        self.assertEqual(source, 'lokal')
        self.assertEqual(len(times), 5)

    def test_cache_never_contacts_network(self):
        self.p.write_month(2026, 9, self.p.parse_month(self.payload, 2026, 9))
        with patch.object(self.p, 'fetch_month', side_effect=AssertionError('network used')):
            self.assertEqual(self.p.get(date(2026, 9, 8))[1], 'cache')

    def test_wrong_day_inside_cache_rejected(self):
        days = self.p.parse_month(self.payload, 2026, 9)
        days['2026-09-08'] = days['2026-09-09']
        self.p.write_month(2026, 9, days)
        self.assertEqual(self.p.get(date(2026, 9, 8), online=False)[1], 'lokal')

    def test_offsets_applied_once_for_cache(self):
        c = Config(latitude=-6.2, longitude=106.8, timezone='Asia/Jakarta', offsets={'Fajr': 3})
        p = Provider(c, Path(self.tmp.name))
        p.write_month(2026, 9, p.parse_month(self.payload, 2026, 9))
        result, source = p.get(date(2026, 9, 8), online=False)
        self.assertEqual(result['Fajr'].strftime('%H:%M'), '04:35')

    def test_fetch_uses_validated_response_and_persists(self):
        from unittest.mock import MagicMock
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(self.payload).encode()
        with patch('adzan.schedule.urlopen', return_value=response):
            result, source = self.p.get(date(2026, 9, 8))
        self.assertEqual(source, 'API')
        self.assertEqual(self.p.get(date(2026, 9, 8), online=False)[0], result)

    def test_local_date_at_international_date_line(self):
        c = Config(latitude=1.8721, longitude=-157.4278, timezone='Pacific/Kiritimati')
        day = date(2026, 9, 8)
        times = calculate(day, c)
        self.assertTrue(all(value.date() == day for value in times.values()))
