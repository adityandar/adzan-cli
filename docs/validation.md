# Validation

Environment: macOS, Python 3.14.6.

- 35 unittest cases passed, with ResourceWarning treated as an error.
- CLI configure, schedule and next tested using subprocesses and temporary paths.
- Calendar parsing, network failure, exact-date cache, corrupt data, location
  isolation, offsets, next-year rollover and international date line covered.
- 150 Jakarta September 2026 prayer times compared against real AlAdhan response:
  maximum local difference 60 seconds.
- Daemon playback exercised with mocked player boundary; durable SQLite claims,
  child termination, stale events and connection cleanup tested.
- `bash -n install.sh` and Python compileall passed.
- Wheel built and installed in a project venv; installed `adzan-cli` entry point
  executed from outside the source tree, configured a temporary location and
  produced an offline schedule successfully.

Not executed on this host: Ubuntu apt installer, physical ALSA playback,
systemd service activation and boot/linger behavior. These require Ubuntu target
hardware with the bundled audio files; follow README for commissioning.

Both supplied MP3 files are included in the wheel. SHA-256 checksums match the originals. New configuration selects the regular and Fajr recordings automatically; both test-audio CLI variants are covered without actual speaker playback.

Location search, unique-name configuration, explicit ID selection, ambiguous noninteractive results and missing results are covered.

## Reminder update — 2026-09-30

47 tests passed with ResourceWarning treated as an error. New coverage includes
legacy config defaults, minute/audio validation, enable/disable/test commands,
midnight reminder timing, stale event skipping, separate durable playback keys,
daemon reminder dispatch, missing audio at startup, and player termination at
adhan time. Playback is mocked; physical audio/systemd remain target-server checks.
