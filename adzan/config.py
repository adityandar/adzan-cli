import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

PRAYERS = ('Fajr', 'Dhuhr', 'Asr', 'Maghrib', 'Isha')
NAMES = dict(zip(PRAYERS, ('Subuh', 'Zuhur', 'Asar', 'Magrib', 'Isya')))
METHODS = {20: ('Kemenag', 20, 18), 3: ('MWL', 18, 17), 2: ('ISNA', 15, 15)}


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as f:
            name = f.name
            json.dump(value, f, indent=2, allow_nan=False)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


@dataclass
class Config:
    latitude: float = -0.0263
    longitude: float = 109.3425
    timezone: str = 'Asia/Pontianak'
    location: str = 'Pontianak'
    method: int = 20
    school: int = 0
    offsets: dict = field(default_factory=dict)
    audio: str = ''
    fajr_audio: str = ''
    audio_device: str = 'alsa/default'
    volume: int = 100
    reminder_minutes: int = 0
    reminder_audio: str = ''

    def __post_init__(self):
        for key, limit in (('latitude', 90), ('longitude', 180)):
            v = getattr(self, key)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or abs(v) > limit:
                raise ValueError(f'{key} harus angka antara {-limit} dan {limit}.')
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError, TypeError) as e:
            raise ValueError('Zona waktu IANA tidak valid, contoh Asia/Jakarta.') from e
        if self.method not in METHODS or self.school not in (0, 1):
            raise ValueError('Metode: 20 (Kemenag), 3 (MWL), 2 (ISNA); school: 0 atau 1.')
        if not isinstance(self.offsets, dict) or any(k not in PRAYERS or type(v) is not int or abs(v) > 60 for k, v in self.offsets.items()):
            raise ValueError('Koreksi harus berupa menit bulat -60..60 per salat.')
        if type(self.volume) is not int or not 0 <= self.volume <= 100:
            raise ValueError('Volume harus 0..100.')
        for key in ('location', 'audio', 'fajr_audio', 'audio_device', 'reminder_audio'):
            if not isinstance(getattr(self, key), str):
                raise ValueError(f'{key} harus berupa teks.')
        if type(self.reminder_minutes) is not int or not 0 <= self.reminder_minutes <= 1439:
            raise ValueError('Reminder harus 0..1439 menit bulat; 0 untuk menonaktifkan.')
        if self.reminder_minutes and not self.reminder_audio.strip():
            raise ValueError('Audio reminder wajib diisi: --reminder-audio /path/reminder.mp3.')

    @property
    def tz(self):
        return ZoneInfo(self.timezone)

    def calculation_key(self):
        return {k: getattr(self, k) for k in ('latitude', 'longitude', 'timezone', 'method', 'school', 'offsets')}

    def save(self, path):
        atomic_json(path, asdict(self))

    @classmethod
    def load(cls, path):
        try:
            return cls(**json.loads(Path(path).read_text()))
        except FileNotFoundError as e:
            raise ValueError('Konfigurasi belum tersedia. Jalankan adzan-cli configure.') from e
        except (TypeError, json.JSONDecodeError) as e:
            raise ValueError(f'Konfigurasi tidak valid: {e}') from e
