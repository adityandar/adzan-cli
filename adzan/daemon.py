import fcntl
import logging
import shutil
import signal
import sqlite3
import subprocess
import threading
import time
from contextlib import closing
from datetime import datetime, timedelta
from .config import NAMES

log = logging.getLogger(__name__)


class Ledger:
    def __init__(self, path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, status TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP)')

    def claim(self, key):
        with closing(sqlite3.connect(self.path)) as db, db:
            return db.execute("INSERT OR IGNORE INTO events(id,status) VALUES (?, 'claimed')", (key,)).rowcount == 1

    def finish(self, key, status):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE events SET status=? WHERE id=?', (status, key))


def due_events(times, now, grace=90):
    return [(name, when) for name, when in times.items() if 0 <= now.timestamp() - when.timestamp() <= grace]


def reminder_events(times, now, config):
    if not config.reminder_minutes:
        return []
    reminders = {name: datetime.fromtimestamp(when.timestamp() - config.reminder_minutes * 60, when.tzinfo)
                 for name, when in times.items() if now.timestamp() < when.timestamp()}
    return due_events(reminders, now)


def player_command(config, prayer):
    audio = config.fajr_audio if prayer == 'Fajr' and config.fajr_audio else config.audio
    if prayer == 'Reminder':
        audio = config.reminder_audio
    return ['mpv', '--no-config', '--no-video', '--no-terminal', '--ao=alsa',
            f'--audio-device={config.audio_device}', f'--volume={config.volume}', '--', audio]


def check_audio(config, reminder_only=False):
    from pathlib import Path
    if not shutil.which('mpv'):
        raise ValueError('mpv belum terpasang. Jalankan sudo apt install mpv.')
    files = [config.reminder_audio] if reminder_only else [config.audio, config.fajr_audio or config.audio]
    if config.reminder_minutes and not reminder_only:
        files.append(config.reminder_audio)
    for audio in files:
        if not audio or not Path(audio).is_file():
            option = '--reminder-audio' if reminder_only or audio == config.reminder_audio else '--audio'
            raise ValueError(f'File audio tidak ditemukan: {audio!r}. Jalankan adzan-cli configure {option} /path/audio.mp3.')


def play(config, prayer, stop, until=None):
    process = subprocess.Popen(player_command(config, prayer))
    try:
        deadline = time.monotonic() + 900
        while process.poll() is None:
            if until is not None and time.time() >= until.timestamp():
                log.info('Reminder dihentikan karena waktu adzan tiba.')
                return True
            if stop.wait(0.2) or time.monotonic() > deadline:
                return False
        return process.returncode == 0
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=0.5 if until is not None else 5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def run(provider, data_dir, offline=False):
    check_audio(provider.config)
    data_dir.mkdir(parents=True, exist_ok=True)
    with (data_dir / 'daemon.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as e:
            raise ValueError('Daemon sudah berjalan untuk direktori data ini.') from e
        stop = threading.Event()
        previous = {}
        for sig in (signal.SIGTERM, signal.SIGINT):
            previous[sig] = signal.signal(sig, lambda *_: stop.set())
        ledger = Ledger(data_dir / 'events.sqlite3')

        def refresh():
            while not stop.is_set():
                errors = provider.sync(datetime.now(provider.config.tz).date())
                stop.wait(900 if errors else 21600)

        if not offline:
            threading.Thread(target=refresh, daemon=True, name='schedule-sync').start()
        log.info('Daemon aktif: %s (%s)', provider.config.location, provider.config.timezone)
        try:
            while not stop.is_set():
                now = datetime.now(provider.config.tz)
                schedules = []
                # Adjacent dates cover offset adjustments across midnight.
                for delta in (-1, 0, 1):
                    day = now.date() + timedelta(days=delta)
                    try:
                        times, source = provider.get(day, online=False)
                    except ValueError as e:
                        log.error('%s', e)
                        stop.wait(60)
                        break
                    schedules.append((day, times, source))
                # Adhan first; re-read the clock after each (blocking) playback.
                for reminder in (False, True):
                    for day, times, source in schedules:
                        now = datetime.now(provider.config.tz)
                        events = reminder_events(times, now, provider.config) if reminder else due_events(times, now)
                        for prayer, when in events:
                            now = datetime.now(provider.config.tz)
                            if not 0 <= now.timestamp() - when.timestamp() <= 90:
                                continue
                            if reminder and now.timestamp() >= times[prayer].timestamp():
                                continue
                            key = f'{day.isoformat()}:{prayer}' + (':reminder' if reminder else '')
                            if stop.is_set() or not ledger.claim(key):
                                continue
                            label = f'Reminder {NAMES[prayer]}' if reminder else NAMES[prayer]
                            log.info('Memutar %s, jadwal %s, sumber %s', label, when.isoformat(), source)
                            try:
                                if reminder:
                                    cutoff = min(t for _, schedule, _ in schedules for t in schedule.values() if t.timestamp() > now.timestamp())
                                    success = play(provider.config, 'Reminder', stop, until=cutoff)
                                else:
                                    success = play(provider.config, prayer, stop)
                            except OSError:
                                log.exception('Pemutar gagal')
                                success = False
                            ledger.finish(key, 'played' if success else 'failed')
                            if not success:
                                log.error('Audio gagal/dihentikan untuk %s; tidak diulang otomatis.', key)
                stop.wait(1)
        finally:
            stop.set()
            for sig, handler in previous.items():
                signal.signal(sig, handler)
