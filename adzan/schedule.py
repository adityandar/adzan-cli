import calendar
import hashlib
import json
import logging
import math
import re
from datetime import date, datetime, time, timedelta
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from .astronomy import calculate
from .config import PRAYERS, atomic_json

log = logging.getLogger(__name__)


class Provider:
    def __init__(self, config, data_dir):
        self.config = config
        key = json.dumps(config.calculation_key(), sort_keys=True)
        self.root = data_dir / 'cache' / hashlib.sha256(key.encode()).hexdigest()[:24]

    def cache_path(self, year, month):
        return self.root / f'{year:04d}-{month:02d}.json'

    def write_month(self, year, month, days):
        atomic_json(self.cache_path(year, month), {'config': self.config.calculation_key(), 'days': days})

    def _decode_day(self, raw):
        result = {k: datetime.fromisoformat(raw[k]) for k in PRAYERS}
        if any(v.tzinfo is None for v in result.values()):
            raise ValueError('Jadwal tanpa zona waktu.')
        result = {k: v.astimezone(self.config.tz) for k, v in result.items()}
        if list(result.values()) != sorted(result.values()) or len(set(result.values())) != 5:
            raise ValueError('Urutan jadwal tidak valid.')
        return result

    def cached(self, day):
        try:
            data = json.loads(self.cache_path(day.year, day.month).read_text())
            if data['config'] != self.config.calculation_key():
                return None
            result = self._decode_day(data['days'][day.isoformat()])
            # Offsets may move an event across midnight, but not by a whole day.
            if any((v - timedelta(minutes=self.config.offsets.get(k, 0))).date() != day for k, v in result.items()):
                return None
            return result
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def parse_month(self, payload, year, month):
        try:
            return self._parse_month(payload, year, month)
        except (TypeError, KeyError, AttributeError, OverflowError) as e:
            raise ValueError('Struktur kalender API tidak valid.') from e

    def _parse_month(self, payload, year, month):
        if payload.get('code') != 200 or not isinstance(payload.get('data'), list):
            raise ValueError('Respons API tidak valid.')
        days = {}
        for row in payload['data']:
            day = datetime.strptime(row['date']['gregorian']['date'], '%d-%m-%Y').date()
            if (day.year, day.month) != (year, month) or day.isoformat() in days:
                raise ValueError('Tanggal API tidak cocok atau duplikat.')
            meta = row['meta']
            if meta['timezone'] != self.config.timezone or meta['method']['id'] != self.config.method:
                raise ValueError('Metode/zona waktu API tidak cocok.')
            if meta['school'] != ('HANAFI' if self.config.school else 'STANDARD'):
                raise ValueError('Metode Asar API tidak cocok.')
            for axis in ('latitude', 'longitude'):
                if not math.isfinite(float(meta[axis])) or abs(float(meta[axis]) - getattr(self.config, axis)) > 0.01:
                    raise ValueError('Koordinat API tidak cocok.')
            raw = {}
            for name in PRAYERS:
                match = re.fullmatch(r'(\d{2}):(\d{2})(?:\s+\([^)]*\))?', row['timings'][name])
                if not match:
                    raise ValueError('Format waktu API tidak valid.')
                h, m = map(int, match.groups())
                value = datetime.combine(day, time(h, m), self.config.tz)
                value += timedelta(minutes=self.config.offsets.get(name, 0))
                raw[name] = value.isoformat()
            self._decode_day(raw)
            days[day.isoformat()] = raw
        if len(days) != calendar.monthrange(year, month)[1]:
            raise ValueError('Kalender API tidak lengkap.')
        return days

    def fetch_month(self, year, month):
        c = self.config
        params = urlencode(dict(latitude=c.latitude, longitude=c.longitude, method=c.method,
                                school=c.school, timezonestring=c.timezone, latitudeAdjustmentMethod=3,
                                tune='0,0,0,0,0,0,0,0,0'))
        request = Request(f'https://api.aladhan.com/v1/calendar/{year}/{month}?{params}',
                          headers={'User-Agent': 'adzan-cli/1.0'})
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read(2_000_000))
        days = self.parse_month(payload, year, month)
        self.write_month(year, month, days)

    def get(self, day, online=True):
        cached = self.cached(day)
        if cached is not None:
            return cached, 'cache'
        if online:
            try:
                self.fetch_month(day.year, day.month)
                cached = self.cached(day)
                if cached is not None:
                    return cached, 'API'
            except (OSError, ValueError, KeyError, TypeError) as e:
                log.warning('API gagal, memakai perhitungan lokal: %s', e)
        return calculate(day, self.config), 'lokal'

    def sync(self, day):
        following = (day.replace(day=1) + timedelta(days=32)).replace(day=1)
        errors = []
        for target in (day, following):
            try:
                self.fetch_month(target.year, target.month)
            except (OSError, ValueError, KeyError, TypeError) as e:
                errors.append(str(e))
                log.warning('Sinkronisasi %s-%s gagal: %s', target.year, target.month, e)
        return errors


def next_prayer(provider, now):
    now = now.astimezone(provider.config.tz)
    candidates = []
    for delta in (-1, 0, 1, 2):
        times, source = provider.get(now.date() + timedelta(days=delta), online=False)
        candidates.extend((name, when, source) for name, when in times.items() if when >= now)
    return min(candidates, key=lambda item: item[1])
