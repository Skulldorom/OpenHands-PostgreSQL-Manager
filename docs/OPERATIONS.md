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

## Persistent conversation identity (OpenHands 1.62.0)

The Docker container name contains a temporary runtime UUID. It is **not** a persistent conversation ID. Starting with the persistent-identity manager, the provisioner reads the verified container bind mount:

```
/var/openhands/conversations/<32-hex-character-conversation-id>
```

The source basename must agree with the destination basename, and the corresponding hyphenated conversation UUID must return HTTP 200 from the authenticated `GET /api/conversations/{conversation_id}` endpoint. Ambiguous or missing mounts fail closed; the manager does not provision an unverified runtime.

The manager stores credentials by persistent conversation ID. When OpenHands resumes a conversation in a new runtime, it reuses the same PostgreSQL database and password and securely copies the credentials into the new container.

### Legacy records

Old `managed.json` records keyed by 64-character Docker container IDs are deliberately **not** cleanup candidates. If the exact old container is still running and the verified mount identifies its persistent conversation, the existing database and credential file can be adopted. Otherwise the orphan is preserved for manual review and a new runtime gets a new conversation-scoped database. Do not delete legacy records or rotate their passwords automatically.

### Safe update

```bash
cd ~/OpenHands-PostgreSQL-Manager
git pull --ff-only
python3 -m unittest discover -s tests -v
bash scripts/install.sh
openhands-postgres-manager status
openhands-postgres-manager provision
openhands-postgres-manager cleanup
```

Provisioning may output no `READY` lines if no conversation containers are currently running. That is normal. Start a new conversation to validate provisioning, suspend it, resume it, and confirm its role and database are unchanged.

**Cleanup remains read-only by default and automatic deletion remains disabled.** Confirm the system's API semantics and full recovery behavior before enabling destructive deletion. There is no guarantee that an observed API 404 is permanent during every lifecycle race.

## Read-only database reconciliation

Run the inventory command after a deployment, suspend/resume test, or before any cleanup decision:

```bash
openhands-postgres-manager audit
```

The inventory compares PostgreSQL's `oh_`-prefixed databases against the manager's state. Categories:

- `ACTIVE_KEEP`: referenced by a persistent conversation with a Docker runtime currently present
- `TRACKED_KEEP`: referenced by a persistent conversation with no current runtime; suspension is expected
- `LEGACY_KEEP`: referenced only by a legacy runtime-keyed state record; not automatically deleted
- `UNTRACKED_KEEP`: database exists but no manager record references it; may be an earlier manual test
- `MISSING_DB_REVIEW`: state references a database not found in PostgreSQL; investigate manually

The command is **strictly read-only** and never purges orphaned resources, rotates passwords, or modifies the manager's state. It intentionally does not claim that any database is safe to delete. The manager also refuses destructive cleanup when a role has more than one state reference, such as an adopted legacy record.

Automatic cleanup is not enabled in the installed systemd unit. Run the inventory first and retain old databases until ownership, actual API deletion semantics, and backup/recovery procedures are validated end-to-end.
