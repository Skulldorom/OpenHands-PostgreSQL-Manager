#!/usr/bin/env bash
set -euo pipefail
[[ $(id -u) -eq 0 ]] || { echo "Run as root on OpenHands LXC" >&2; exit 1; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
install -d -m 700 /opt/openhands-postgres
install -m 700 "$ROOT/openhands-postgres-manager" /usr/local/sbin/openhands-postgres-manager
for file in "$ROOT"/systemd/*; do
  install -m 644 "$file" "/etc/systemd/system/$(basename "$file")"
done
systemctl daemon-reload
echo "Installed, timers NOT automatically enabled."
echo "Check status: /usr/local/sbin/openhands-postgres-manager status"
echo "Dry run cleanup: /usr/local/sbin/openhands-postgres-manager cleanup"
echo "After validation: systemctl enable --now openhands-postgres-provision.timer"
