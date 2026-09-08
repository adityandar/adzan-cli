"""Solar-angle fallback; equations documented at https://praytimes.org/calculation.

Independent implementation, sea-level horizon; not an official published timetable.
Polar days/nights without sunrise/sunset are rejected explicitly.
"""
import math
from datetime import datetime, time, timedelta, timezone
from .config import METHODS, PRAYERS


def sin(x):
    return math.sin(math.radians(x))


def cos(x):
    return math.cos(math.radians(x))


def solar(jd):
    d = jd - 2451545.0
    g = (357.529 + 0.98560028 * d) % 360
    q = (280.459 + 0.98564736 * d) % 360
    longitude = q + 1.915 * sin(g) + 0.020 * sin(2 * g)
    e = 23.439 - 0.00000036 * d
    ra = math.degrees(math.atan2(cos(e) * sin(longitude), cos(longitude))) / 15 % 24
    eq = (q / 15 - ra + 12) % 24 - 12
    dec = math.degrees(math.asin(sin(e) * sin(longitude)))
    return dec, eq


def calculate(day, config):
    base = datetime.combine(day, time(), timezone.utc)
    # Political timezones can place solar noon on a different UTC date.
    approximate_noon = base + timedelta(hours=12 - config.longitude / 15)
    base -= timedelta(days=(approximate_noon.astimezone(config.tz).date() - day).days)
    jd = base.timestamp() / 86400 + 2440587.5
    lat, lon = config.latitude, config.longitude

    def event(altitude, morning=False, asr=False):
        hour = 12 - lon / 15
        for _ in range(4):
            dec, eq = solar(jd + hour / 24)
            noon = 12 - lon / 15 - eq
            if altitude is None:
                hour = noon
                continue
            alt = altitude
            if asr:
                alt = math.degrees(math.atan(1 / (1 + config.school + math.tan(math.radians(abs(lat - dec))))))
            ratio = (sin(alt) - sin(lat) * sin(dec)) / (cos(lat) * cos(dec))
            if abs(ratio) > 1:
                return None
            arc = math.degrees(math.acos(ratio)) / 15
            hour = noon + (-arc if morning else arc)
        return hour

    sunrise, sunset = event(-0.833, True), event(-0.833)
    if sunrise is None or sunset is None:
        raise ValueError('Perhitungan lokal tidak tersedia untuk siang/malam kutub; gunakan jadwal otoritas lokal.')
    _, fajr_angle, isha_angle = METHODS[config.method]
    fajr, isha = event(-fajr_angle, True), event(-isha_angle)
    # AlAdhan latitudeAdjustmentMethod=3 (angle based).
    night = 24 - (sunset - sunrise)
    fajr = max(fajr if fajr is not None else -math.inf, sunrise - night * fajr_angle / 60)
    isha = min(isha if isha is not None else math.inf, sunset + night * isha_angle / 60)
    values = (fajr, event(None), event(0, asr=True), sunset, isha)
    result = {}
    for name, hour in zip(PRAYERS, values):
        if hour is None:
            raise ValueError(f'Waktu {name} tidak dapat dihitung di lokasi ini.')
        # Match API minute rounding, then apply user adjustments exactly once.
        minutes = math.floor(hour * 60 + 0.5) + config.offsets.get(name, 0)
        result[name] = (base + timedelta(minutes=minutes)).astimezone(config.tz)
    return result
