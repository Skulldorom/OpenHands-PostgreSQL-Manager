# Operations

## Existing host prerequisites

- Debian/OpenHands LXC with root-controlled Docker CLI and systemd.
- `openhands-postgres` PostgreSQL 17 container already running and healthy.
- Database listener reachable inside conversation containers at `172.17.0.1:55432`.
- Host directory `/opt/openhands-postgres` mode 0700.
- OpenHands agent skills load `/tmp/openhands-postgres.env` when present.

## Installation

```bash
git clone https://github.com/Skulldorom/OpenHands-PostgreSQL-Manager.git
cd OpenHands-PostgreSQL-Manager
sudo bash scripts/install.sh
sudo /usr/local/sbin/openhands-postgres-manager status
sudo /usr/local/sbin/openhands-postgres-manager provision
sudo /usr/local/sbin/openhands-postgres-manager provision
sudo systemctl enable --now openhands-postgres-provision.timer
```

Do not enable deletion until authenticated OpenHands API semantics have been verified. The installer does not start or modify the PostgreSQL container, alter Agent Canvas, or enable timers automatically.

## Recovery and existing databases

A saved `<full-container-id>.env` allows an interrupted run to resume. A role and database that predate the manager without matching credentials are *not* adopted; recovery requires manual verification. The manager never resets unknown passwords automatically. Keep backups of `/opt/openhands-postgres` and the Docker volume securely.

## Troubleshooting

```bash
docker inspect openhands-postgres --format '{{.State.Health.Status}}'
systemctl status openhands-postgres-provision.timer --no-pager
journalctl -u openhands-postgres-provision.service -n 50 --no-pager
/usr/local/sbin/openhands-postgres-manager status
/usr/local/sbin/openhands-postgres-manager cleanup
```

## Cleanup

`cleanup` is read-only except for printing; it does not advance the retention timer. An explicit `cleanup --apply`, with the deletion environment gate, starts the first-404 grace period and may delete eligible entries on future runs. Dry-run cleanup timers therefore **do not** automatically reclaim storage. Configure automatic destructive cleanup only after local end-to-end verification.

## Removal

```bash
sudo bash scripts/uninstall.sh
```

This leaves PostgreSQL server, databases, volumes and credentials untouched.

## Agent Server API diagnostics (OpenHands 1.62.0)

This version exposes `GET /api/conversations/{conversation_id}` on the host-local Agent Server at port 18000. Older versions of this project incorrectly queried `/conversations/{conversation_id}`. Upgrade before investigating deletion cleanup.

Provisioning is independent of this API and can remain enabled. Cleanup will print `SKIP cleanup: no valid positive API control` unless an authenticated `200` is verified for an active conversation. That is a **safe block**, not authorization to enable deletion.

Inspect the live API specification without displaying credentials:

```bash
python3 - <<'PY'
import json, urllib.request
spec=json.load(urllib.request.urlopen("http://127.0.0.1:18000/openapi.json", timeout=5))
print(spec.get("paths", {}).get("/api/conversations/{conversation_id}", {}))
PY
```

The container name's UUID may identify a *runtime* rather than the persistent conversation. Validate that the ID maps to the actual conversation returned by the API before relying on 404s. Cleanup remains opt-in. Do not assume a 404 proves deletion without independent validation of API authorization and response semantics.

After updating the repository on the LXC, redeploy the executable and restart only the provisioning timer if required:

```bash
git pull --ff-only
bash scripts/install.sh
openhands-postgres-manager status
openhands-postgres-manager cleanup
```
