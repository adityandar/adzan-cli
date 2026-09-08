# adzan-cli

Approved scope: Python 3.10+ CLI and systemd service for headless Ubuntu 22.04+.
Configure coordinates, IANA timezone, method, per-prayer offsets, local audio and
optional Fajr audio. AlAdhan monthly calendars are validated and atomically cached
by calculation configuration. Fetch current and next month. Exact-date cache then
local astronomical calculation handles outages. Local results are labeled and are
not represented as official Kemenag timetables. Support Kemenag, MWL and ISNA.

Commands: configure, schedule, next, sync, test-audio, run. JSON output for schedule
and next; offline switch; live countdown. mpv uses ALSA on headless Linux.
Daemon reads disk/local data only in its timing loop. A background worker refreshes
calendars with bounded requests. Persistent SQLite claims prevent duplicate playback
across restarts; one daemon per data directory via flock. Missed events older than
90 seconds are skipped. Claim before playback favors no duplicate audio after crashes;
failed/interrupted playback is logged, not automatically replayed. SIGTERM stops audio.
User-provided regular and Fajr MP3 files are bundled as package data and selected during first setup. Terminal command is adzan-cli; internal Python module and service remain adzan.
CLI and service share config and data paths. Ubuntu installer creates venv, config
and systemd service under the invoking user, with explicit documented sudo commands.

Location search uses Open-Meteo/GeoNames. `locations QUERY` lists IDs, names and
timezones; configure accepts a name with interactive disambiguation or an explicit
location ID. Manual coordinates remain supported for offline setup.
