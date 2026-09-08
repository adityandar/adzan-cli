import argparse
import json
import logging
import os
import sqlite3
import sys
import threading
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from .config import Config, METHODS, NAMES
from .daemon import check_audio, play, run
from .schedule import Provider, next_prayer
from . import locations


def parser():
    p = argparse.ArgumentParser(prog='adzan-cli', description='Jadwal salat dan adzan otomatis untuk Ubuntu headless.')
    p.add_argument('--config', type=Path, default=Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'adzan/config.json')
    p.add_argument('--data-dir', type=Path, default=Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'adzan')
    commands = p.add_subparsers(dest='command', required=True)
    c = commands.add_parser('locations', help='Cari nama kota, koordinat dan zona waktu')
    c.add_argument('query')
    c.add_argument('--country', help='Filter kode negara, contoh ID')
    c.add_argument('--json', action='store_true')
    c = commands.add_parser('configure', help='Atur lokasi, metode dan audio; tanpa opsi membuka panduan interaktif')
    c.add_argument('--latitude', type=float)
    c.add_argument('--longitude', type=float)
    c.add_argument('--timezone')
    c.add_argument('--location')
    c.add_argument('--location-id', type=int, help='ID dari perintah locations')
    c.add_argument('--country', help='Filter pencarian negara, contoh ID')
    c.add_argument('--method', type=int, choices=METHODS)
    c.add_argument('--school', type=int, choices=(0, 1))
    c.add_argument('--audio')
    c.add_argument('--fajr-audio')
    c.add_argument('--audio-device')
    c.add_argument('--volume', type=int)
    c.add_argument('--offset', action='append', metavar='Fajr=2', help='Nama API: Fajr,Dhuhr,Asr,Maghrib,Isha; menit -60..60')
    for name, help_text in [('schedule', 'Jadwal salat'), ('next', 'Salat berikutnya dan hitung mundur')]:
        c = commands.add_parser(name, help=help_text)
        c.add_argument('--offline', action='store_true', help='Gunakan cache atau perhitungan lokal tanpa jaringan')
        c.add_argument('--json', action='store_true')
        if name == 'schedule':
            c.add_argument('--date', type=date.fromisoformat)
        else:
            c.add_argument('--watch', action='store_true')
    commands.add_parser('sync', help='Perbarui cache bulan ini dan berikutnya')
    c = commands.add_parser('test-audio', help='Putar audio sekarang')
    c.add_argument('--fajr', action='store_true')
    c = commands.add_parser('run', help='Jalankan daemon di foreground')
    c.add_argument('--offline', action='store_true')
    return p


def configure(args):
    exists = args.config.exists()
    old = Config.load(args.config) if exists else Config()
    values = asdict(old)
    if not exists:
        audio_dir = Path(__file__).resolve().parent / 'audio'
        values['audio'] = str(audio_dir / 'adhan.mp3')
        values['fajr_audio'] = str(audio_dir / 'adhan-fajr.mp3')
    manual = any(getattr(args, k) is not None for k in ('latitude', 'longitude', 'timezone'))
    if args.location_id is not None and (manual or args.location):
        raise ValueError('--location-id tidak dapat digabungkan dengan nama/koordinat manual.')
    resolved = None
    if args.location_id is not None:
        resolved = locations.by_id(args.location_id)
    elif args.location and not manual:
        resolved = locations.choose(args.location, args.country)
    if resolved:
        values.update(locations.fields(resolved))
    changed = any(getattr(args, key, None) is not None for key in values) or args.offset or resolved
    if not changed:
        if not sys.stdin.isatty():
            raise ValueError('Gunakan configure --location NAMA atau --location-id ID.')
        query = input(f"Cari nama kota [{values['location']}]: ").strip()
        if query or not exists:
            values.update(locations.fields(locations.choose(query or values['location'])))
        for key, prompt, cast in [('audio', 'Path MP3 adzan', str), ('fajr_audio', 'Path MP3 Subuh (opsional)', str)]:
            answer = input(f'{prompt} [{values[key]}]: ').strip()
            if answer:
                values[key] = cast(answer)
    else:
        if not exists and not resolved and any(getattr(args, k) is None for k in ('latitude', 'longitude', 'timezone')):
            raise ValueError('Setup awal memerlukan --latitude, --longitude dan --timezone.')
        for key in values:
            if getattr(args, key, None) is not None and not (resolved and key == 'location'):
                values[key] = getattr(args, key)
    for item in args.offset or []:
        name, minutes = item.split('=', 1)
        values['offsets'][name] = int(minutes)
    for key in ('audio', 'fajr_audio'):
        if values[key]:
            path = Path(values[key]).expanduser().resolve()
            if not path.is_file():
                raise ValueError(f'File audio tidak ditemukan: {path}')
            values[key] = str(path)
    Config(**values).save(args.config)
    print(f'Konfigurasi tersimpan: {args.config}')
    print('Jika layanan sedang berjalan: systemctl --user restart adzan')


def remaining(seconds):
    seconds = max(0, int(seconds))
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f'{h:02d}:{m:02d}:{s:02d}'


def main(argv=None):
    args = parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    try:
        if args.command == 'locations':
            rows = locations.search(args.query, args.country)
            if args.json:
                print(json.dumps(rows))
            else:
                locations.show(rows)
            return 0
        if args.command == 'configure':
            configure(args)
            return 0
        config = Config.load(args.config)
        provider = Provider(config, args.data_dir)
        now = datetime.now(config.tz)
        if args.command == 'sync':
            errors = provider.sync(now.date())
            if errors:
                print('Sinkronisasi belum lengkap; cache lama tetap tersedia.', file=sys.stderr)
                return 1
            print('Cache bulan ini dan berikutnya diperbarui.')
        elif args.command == 'schedule':
            day = args.date or now.date()
            times, source = provider.get(day, online=not args.offline)
            if args.json:
                print(json.dumps({'date': day.isoformat(), 'location': config.location, 'timezone': config.timezone,
                                  'source': source, 'prayers': {k: v.isoformat() for k, v in times.items()}}))
            else:
                print(f'{config.location} | {day} | {config.timezone} | {METHODS[config.method][0]} | sumber: {source}')
                for name, when in times.items():
                    print(f'{NAMES[name]:8} {when:%H:%M}')
        elif args.command == 'next':
            if args.watch and args.json:
                raise ValueError('--watch tidak dapat digabungkan dengan --json.')
            if not args.offline:
                provider.get(now.date())
                provider.get(now.date() + timedelta(days=1))
            while True:
                now = datetime.now(config.tz)
                name, when, source = next_prayer(provider, now)
                seconds = max(0, int(when.timestamp() - now.timestamp()))
                if args.json:
                    print(json.dumps({'prayer': name, 'name': NAMES[name], 'time': when.isoformat(),
                                      'remaining_seconds': seconds, 'source': source}))
                else:
                    text = f'{NAMES[name]} — {when:%Y-%m-%d %H:%M} {config.timezone} — dalam {remaining(seconds)} — sumber: {source}'
                    print(('\r' if args.watch else '') + text + ('   ' if args.watch else ''), end='' if args.watch else '\n', flush=True)
                if not args.watch:
                    break
                threading.Event().wait(1)
        elif args.command == 'test-audio':
            check_audio(config)
            return 0 if play(config, 'Fajr' if args.fajr else 'Dhuhr', threading.Event()) else 1
        elif args.command == 'run':
            run(provider, args.data_dir, args.offline)
        return 0
    except (ValueError, OSError, sqlite3.Error, EOFError) as e:
        print(f'Kesalahan: {e}', file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print()
        return 130
