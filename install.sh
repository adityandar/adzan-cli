#!/usr/bin/env bash
set -euo pipefail
if [[ $(uname -s) != Linux ]]; then
  echo 'Installer ini untuk Ubuntu/Linux dengan systemd.' >&2
  exit 1
fi
if [[ $EUID -eq 0 ]]; then
  echo 'Jalankan sebagai user biasa, bukan sudo. Lihat README untuk dependensi apt.' >&2
  exit 1
fi
# Fixed locations match systemd unit. Avoid silent XDG config/data mismatches.
if [[ -n ${XDG_CONFIG_HOME:-} && $XDG_CONFIG_HOME != "$HOME/.config" ]] ||
   [[ -n ${XDG_DATA_HOME:-} && $XDG_DATA_HOME != "$HOME/.local/share" ]]; then
  echo 'Installer memerlukan lokasi XDG standar; gunakan instalasi manual untuk lokasi khusus.' >&2
  exit 1
fi
command -v mpv >/dev/null || { echo 'Pasang dependensi: sudo apt install python3-venv mpv alsa-utils' >&2; exit 1; }
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
venv_dir="$HOME/.local/share/adzan/venv"
python3 -m venv "$venv_dir"
"$venv_dir/bin/python" -m pip install "$project_dir"
mkdir -p "$HOME/.local/bin" "$HOME/.config/systemd/user"
ln -sfn "$venv_dir/bin/adzan-cli" "$HOME/.local/bin/adzan-cli"
install -m 644 "$project_dir/systemd/adzan.service" "$HOME/.config/systemd/user/adzan.service"
systemctl --user daemon-reload
printf '%s\n' 'Terpasang. Berikutnya:' \
  "$HOME/.local/bin/adzan-cli configure" \
  "$HOME/.local/bin/adzan-cli test-audio" \
  'systemctl --user enable --now adzan' \
  "sudo loginctl enable-linger $(id -un)"
