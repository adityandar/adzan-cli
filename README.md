# adzan-cli

Aplikasi terminal untuk memutar adzan otomatis pada lima waktu salat, tanpa desktop.
Python 3.10+, Ubuntu 22.04 atau lebih baru, systemd, mpv dan perangkat audio ALSA.
Audio dimainkan pada **mesin server**, bukan laptop yang membuka SSH.

## Getting Started — install lewat SSH

Panduan ini untuk Ubuntu Server 22.04 atau lebih baru. Login melalui SSH sebagai
**user biasa yang bisa memakai `sudo`**, bukan root. Siapkan speaker yang terhubung
ke server dan koneksi internet untuk instalasi serta pencarian lokasi.

### 1. Install aplikasi

Salin dan jalankan perintah berikut satu per satu:

```bash
sudo apt update
sudo apt install -y git python3-venv mpv alsa-utils

git clone https://github.com/adityandar/adzan-cli.git
cd adzan-cli
./install.sh

export PATH="$HOME/.local/bin:$PATH"
```

Agar perintah tersedia pada sesi SSH berikutnya, tambahkan baris
`export PATH="$HOME/.local/bin:$PATH"` ke `~/.profile` jika belum ada.

### 2. Pilih kotamu

```bash
adzan-cli configure --location Pontianak
```

Ganti `Pontianak` dengan nama kotamu. Untuk nama yang mengandung spasi, gunakan
tanda kutip, misalnya `--location "Jakarta Selatan"`. Jika ada beberapa hasil,
pilih nomor lokasi yang sesuai. Koordinat dan zona waktu terisi otomatis;
audio adzan biasa dan Subuh sudah disertakan.

### 3. Cek jadwal dan tes suara

```bash
adzan-cli sync
adzan-cli schedule
adzan-cli next

adzan-cli test-audio
adzan-cli test-audio --fajr
```

`schedule` menampilkan jadwal hari ini, sedangkan `next` menampilkan waktu menuju
salat berikutnya. Dua perintah terakhir langsung memutar audio untuk mengecek
speaker. **Suara keluar dari server, bukan laptop yang dipakai SSH.** Jika muncul
masalah izin audio, lanjutkan langkah 4, lalu ulangi tes setelah reboot.

### 4. Aktifkan otomatis saat server menyala

```bash
sudo usermod -aG audio "$USER"
sudo loginctl enable-linger "$USER"
sudo timedatectl set-ntp true
systemctl --user enable --now adzan
```

Perintah di atas memberi akses audio, menjaga service berjalan tanpa login,
menyinkronkan jam server, dan mengaktifkan adzan otomatis. Terapkan perubahan
grup audio dengan reboot saat server siap direstart:

```bash
sudo reboot
```

Koneksi SSH akan terputus. Tunggu server menyala, lalu login kembali.

### 5. Pastikan service aktif

```bash
systemctl --user status adzan
journalctl --user -u adzan -n 50 --no-pager
```

Cari status **`active (running)`**. Nama service adalah `adzan`, sementara perintah
terminalnya `adzan-cli`. Layanan tetap berjalan setelah SSH ditutup.

Jika suara belum keluar, periksa perangkat dan volume:

```bash
aplay -l
alsamixer
adzan-cli test-audio
```

Pastikan speaker terhubung dan tidak mute. Jika `adzan-cli` tidak ditemukan setelah
login ulang, jalankan `export PATH="$HOME/.local/bin:$PATH"` lagi.
Pengaturan lebih lanjut dijelaskan di bagian-bagian berikut.

## Setup dan konfigurasi

Jalankan dari folder proyek sebagai user biasa:

```bash
sudo apt update
sudo apt install python3-venv mpv alsa-utils
./install.sh
export PATH="$HOME/.local/bin:$PATH"
adzan-cli configure
```

Installer membuat virtualenv di `~/.local/share/adzan/venv`, memasang perintah
`~/.local/bin/adzan-cli`, dan menyalin service systemd user. Installer tidak otomatis
mengaktifkan service. Tambahkan ekspor PATH di atas ke `~/.profile` bila diperlukan.

Setup interaktif meminta nama kota, menampilkan hasil pencarian bila ada beberapa
lokasi, lalu mengisi koordinat dan zona waktu otomatis.
Tekan Enter pada pilihan audio untuk memakai rekaman bawaan.
Cari lokasi tanpa mengatur konfigurasi terlebih dahulu:

```bash
adzan-cli locations Pontianak
adzan-cli locations "Bandung" --country ID
adzan-cli locations Jakarta --json
adzan-cli configure --location Pontianak --country ID
```

Jika beberapa kota cocok, terminal interaktif meminta nomor pilihan. Untuk skrip,
gunakan `adzan-cli configure --location-id ID` dengan ID dari daftar hasil agar
lokasi tidak dipilih sembarangan. Nama, provinsi, negara, koordinat dan zona waktu
terlihat pada daftar. Pencarian memakai internet; setelah setup, jadwal tetap
mendukung cache/offline. Data lokasi: [Open-Meteo](https://open-meteo.com/en/docs/geocoding-api)
dan [GeoNames](https://www.geonames.org/).

Koordinat manual tetap tersedia untuk alamat yang lebih presisi atau setup offline:

```bash
adzan-cli configure --location Pontianak \
  --latitude -0.0263 --longitude 109.3425 --timezone Asia/Pontianak
```

Dua file audio sudah disertakan dan dipilih otomatis saat setup baru:
`adzan/audio/adhan.mp3` untuk adzan biasa dan `adzan/audio/adhan-fajr.mp3` untuk
Subuh. Tidak perlu menentukan path audio saat setup. Untuk mengganti file audio:

```bash
adzan-cli configure --audio "$HOME/Music/adzan.mp3"
adzan-cli configure --fajr-audio "$HOME/Music/adzan-subuh.mp3"
adzan-cli test-audio
adzan-cli test-audio --fajr
adzan-cli sync
adzan-cli schedule
adzan-cli next
adzan-cli next --watch
```

## Autostart saat boot, termasuk tanpa login

Untuk audio headless, tambahkan user service ke grup `audio`:

```bash
sudo usermod -aG audio "$USER"
sudo loginctl enable-linger "$USER"
sudo timedatectl set-ntp true
```

Logout/login atau reboot agar grup baru aktif; user manager yang sudah berjalan
mungkin tetap menyimpan grup lama sampai restart/reboot. Lalu:

```bash
systemctl --user enable --now adzan
systemctl --user status adzan
journalctl --user -u adzan -f
```

Linger membuat service user berjalan saat boot dan tetap hidup setelah SSH putus.
Konfigurasi dan direktori data harus sama antara CLI dan service. Unit file bawaan
menggunakan direktori HOME standar; untuk XDG khusus atau flag `--config`/
`--data-dir`, sesuaikan `ExecStart` melalui `systemctl --user edit adzan`.

Setelah mengganti konfigurasi:

```bash
systemctl --user restart adzan
```

Menghentikan atau menonaktifkan:

```bash
systemctl --user stop adzan
systemctl --user disable adzan
```

## Jadwal, akurasi, dan mode offline

1. AlAdhan menyediakan kalender bulanan berdasarkan koordinat dan zona waktu.
2. `sync` dan background worker mengambil bulan ini dan berikutnya. Daemon
   memperbarui setiap 6 jam, mencoba lagi 15 menit setelah kegagalan.
3. Cache valid digunakan lebih dulu. Jika kosong, perintah CLI mencoba API,
   lalu memakai fallback offline bila API gagal. Proses playback tidak menunggu request API.
4. Cache dipisahkan menurut koordinat, zona waktu, metode, mazhab Asar dan koreksi.
   Kalender parsial, metadata salah, tanggal tertukar atau JSON rusak ditolak.
5. Sumber `API`, `cache`, atau `lokal` ditampilkan di terminal/JSON. Jadwal tanggal
   lain tidak dipakai sebagai pengganti jadwal hari ini.

```bash
adzan-cli schedule --date 2026-09-08 --offline
adzan-cli schedule --json
adzan-cli next --offline --json
adzan-cli run --offline
```

Metode yang didukung (sudut Subuh/Isya): Kemenag `20` (20°/18°), MWL `3`
(18°/17°), ISNA `2` (15°/15°). Asar standar `--school 0`, Hanafi `--school 1`.
Koreksi berlaku pada API maupun lokal, tepat satu kali:

```bash
adzan-cli configure --method 20 --school 0 --offset Dhuhr=2 --offset Maghrib=2
```

Koreksi -60..60 menit. Gunakan nama `Fajr`, `Dhuhr`, `Asr`, `Maghrib`, `Isha`;
set 0 untuk menghapus efek koreksi. Tidak ada tambahan ihtiyat tersembunyi:
request API memakai `tune=0,...,0`, penyesuaian ditentukan pengguna. Sudut metode
Kemenag bukan jaminan identik dengan jadwal resmi Kemenag/masjid setempat.

Fallback menghitung posisi matahari, memakai horizon permukaan laut dan pembulatan
ke menit terdekat. Penyesuaian lintang tinggi menggunakan proporsi sudut malam;
siang/malam kutub tanpa terbit/terbenam matahari ditolak dengan pesan eksplisit.
Tidak ada koreksi elevasi. Pilih zona waktu yang sesuai dengan koordinat.

Pengujian fixture AlAdhan untuk Jakarta September 2026 (150 waktu salat)
menunjukkan selisih lokal maksimum 1 menit; ini bukan jaminan untuk semua lokasi,
tanggal, ketinggian, atau jadwal otoritas lokal. Cocokkan dengan jadwal setempat
saat setup dan atur koreksi bila diperlukan. Ketepatan pemutaran juga bergantung
pada jam server; gunakan sinkronisasi NTP.

Referensi: [AlAdhan methods](https://api.aladhan.com/v1/methods),
[AlAdhan API](https://aladhan.com/prayer-times-api),
[rumus astronomi](https://praytimes.org/calculation).

## Cara kerja service

- Memeriksa waktu setiap detik, tanpa GUI dan tanpa stream audio internet.
- Grace period 90 detik: adzan masih diputar jika terlambat maksimal 90 detik.
  Jadwal yang lebih lama terlewat saat server mati akan dilewati.
- SQLite menandai jadwal sebelum audio diputar untuk mencegah playback ganda,
  termasuk setelah restart atau perubahan jam. Jika aplikasi crash setelah
  penandaan, jadwal itu tidak di-retry otomatis. Error playback masuk ke log.
- Lock mencegah dua daemon memakai direktori data yang sama. Hindari menjalankan
  daemon kedua dengan direktori data berbeda pada speaker yang sama.
- SIGTERM menghentikan audio player; durasi playback dibatasi maksimum 15 menit.
- `test-audio` memutar audio secara manual tanpa menandai jadwal sebagai sudah diputar.
- Konfigurasi: `~/.config/adzan/config.json`; cache/ledger:
  `~/.local/share/adzan/`. Ledger menyimpan riwayat playback untuk mencegah adzan diputar dua kali; jangan dihapus.

## Audio troubleshooting

```bash
aplay -l
mpv --audio-device=help
adzan-cli configure --audio-device 'alsa/plughw:CARD=Device,DEV=0' --volume 80
adzan-cli test-audio
```

Gunakan nama perangkat yang benar-benar muncul pada mesin Anda. Default
`alsa/default` menggunakan perangkat ALSA default. Jika diam, periksa speaker,
volume/mute melalui `alsamixer`, izin `/dev/snd`, grup audio, dan log service.
Untuk server VM/cloud, pastikan audio device tersedia, misalnya melalui device passthrough.

## Development / instalasi manual

```bash
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/adzan-cli --help
python3 -m unittest discover -s tests -v
```

Tanpa instalasi paket: `python3 -m adzan --help`. Flag global harus diletakkan
sebelum subcommand, misalnya `adzan-cli --config /path/config.json schedule`.
Runtime Python hanya memakai standard library; pip membutuhkan setuptools saat
build. Installer memerlukan koneksi untuk build tooling jika belum tersedia.

Pengujian tidak memutar audio nyata. Integrasi ALSA dan boot systemd perlu
diverifikasi di Ubuntu target; lingkungan pengembangan proyek ini macOS.
