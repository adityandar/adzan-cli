import importlib.util
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory


class Availability(unittest.TestCase):
    def test_application_exists(self):
        self.assertIsNotNone(importlib.util.find_spec('adzan.config'))


if importlib.util.find_spec('adzan.config'):
    from adzan.config import Config
    from adzan.astronomy import calculate
    from adzan.schedule import Provider, next_prayer
    from adzan.daemon import Ledger, due_events, player_command

    class ConfigTests(unittest.TestCase):
        def test_invalid_values(self):
            for kwargs in ({'latitude': 91}, {'longitude': float('nan')},
                           {'timezone': 'Mars/Foo'}, {'method': 99},
                           {'offsets': {'Fajr': 1000}}, {'volume': -1}):
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                    Config(**kwargs)

        def test_roundtrip(self):
            with TemporaryDirectory() as d:
                path = Path(d) / 'config.json'
                c = Config(latitude=-6.2, longitude=106.8)
                c.save(path)
                self.assertEqual(Config.load(path), c)

    class AstronomyTests(unittest.TestCase):
        def test_jakarta_reference(self):
            c = Config(latitude=-6.2, longitude=106.8)
            times = calculate(date(2026, 9, 8), c)
            expected = {'Fajr': '04:34', 'Dhuhr': '11:52', 'Asr': '15:09',
                        'Maghrib': '17:53', 'Isha': '19:02'}
            for name, value in expected.items():
                h, m = map(int, value.split(':'))
                actual = times[name].hour * 60 + times[name].minute
                self.assertLessEqual(abs(actual - h * 60 - m), 6, name)

        def test_offsets(self):
            day = date(2026, 9, 8)
            base = calculate(day, Config())
            tuned = calculate(day, Config(offsets={'Fajr': 3}))
            self.assertEqual(tuned['Fajr'] - base['Fajr'], timedelta(minutes=3))

        def test_polar_unavailable_is_explicit(self):
            with self.assertRaises(ValueError):
                calculate(date(2026, 6, 21), Config(latitude=89))

    class ProviderTests(unittest.TestCase):
        def setUp(self):
            self.tmp = TemporaryDirectory()
            self.addCleanup(self.tmp.cleanup)
            self.c = Config()
            self.p = Provider(self.c, Path(self.tmp.name))

        def test_offline_fallback_and_next_day(self):
            day = date(2026, 12, 31)
            times, source = self.p.get(day, online=False)
            self.assertEqual(source, 'lokal')
            now = datetime(2026, 12, 31, 23, 59, tzinfo=self.c.tz)
            name, when, source = next_prayer(self.p, now)
            self.assertEqual(name, 'Fajr')
            self.assertEqual(when.date(), date(2027, 1, 1))
            self.assertGreater(when, now)

        def test_cache_roundtrip_and_location_isolation(self):
            day = date(2026, 9, 8)
            times = calculate(day, self.c)
            self.p.write_month(2026, 9, {day.isoformat():
                {k: v.isoformat() for k, v in times.items()}})
            cached, source = self.p.get(day, online=False)
            self.assertEqual(source, 'cache')
            self.assertEqual(cached, times)
            other = Provider(Config(latitude=2), Path(self.tmp.name))
            self.assertEqual(other.get(day, online=False)[1], 'lokal')

        def test_corrupt_cache_falls_back(self):
            self.p.cache_path(2026, 9).parent.mkdir(parents=True, exist_ok=True)
            self.p.cache_path(2026, 9).write_text('{bad')
            self.assertEqual(self.p.get(date(2026, 9, 8), online=False)[1], 'lokal')

    class PlaybackTests(unittest.TestCase):
        def test_claim_survives_restart(self):
            with TemporaryDirectory() as d:
                path = Path(d) / 'events.sqlite3'
                self.assertTrue(Ledger(path).claim('2026-09-08:Fajr'))
                self.assertFalse(Ledger(path).claim('2026-09-08:Fajr'))

        def test_late_events_are_skipped(self):
            times = calculate(date(2026, 9, 8), Config())
            now = times['Fajr'] + timedelta(seconds=30)
            self.assertEqual([n for n, t in due_events(times, now)], ['Fajr'])
            self.assertEqual(list(due_events(times, now + timedelta(minutes=2))), [])

        def test_player_uses_literal_path(self):
            c = Config(audio='/tmp/adhan $(touch evil).mp3')
            command = player_command(c, 'Fajr')
            self.assertEqual(command[-2:], ['--', c.audio])
            self.assertIn('--ao=alsa', command)
