#!/usr/bin/env bash
set -euo pipefail
[[ $(id -u) -eq 0 ]] || exit 1
systemctl disable --now openhands-postgres-provision.timer openhands-postgres-cleanup.timer 2>/dev/null || true
rm -f /etc/systemd/system/openhands-postgres-{provision,cleanup}.{service,timer}
rm -f /usr/local/sbin/openhands-postgres-manager
systemctl daemon-reload
echo "Uninstalled manager. PostgreSQL container, databases and credentials retained."
