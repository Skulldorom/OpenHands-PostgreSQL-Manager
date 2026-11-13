# OpenHands PostgreSQL Manager

Self-hosted, host-side PostgreSQL test database provisioning for isolated [OpenHands](https://github.com/All-Hands-AI/OpenHands) Agent Canvas conversation containers.

**Status:** initial implementation; validate against your OpenHands API and deployment before enabling destructive cleanup.

## Why

OpenHands conversation containers can run with `CapDrop: ALL` and `no-new-privileges`. They can't reliably install and run PostgreSQL internally or launch additional Docker containers. This manager runs **on the LXC/Docker host** and gives each new conversation a dedicated PostgreSQL 17 database and restricted login. Agents only receive their own connection credentials.

## Capabilities

- Detects running `agent-server-conversation-<UUID>` containers
- Creates an `oh_<hash>` database/role per runtime
- Stores credentials in a host directory (0700; files 0600)
- Copies `/tmp/openhands-postgres.env` into the agent runtime without changing container privileges
- Retries idempotently; preserves existing credentials and refuses unknown state
- Verifies authentication and database ownership
- Provides systemd provisioning timer (one-minute polling)
- Provides conservative deletion analysis with authenticated API checks and 24-hour grace
- Ships a non-destructive cleanup timer; **automatic destructive deletion is off**

## Quick start

Your PostgreSQL service must already be running and healthy as `openhands-postgres`, accessible by conversation containers at `172.17.0.1:55432`.

```bash
git clone https://github.com/Skulldorom/OpenHands-PostgreSQL-Manager.git
cd OpenHands-PostgreSQL-Manager
sudo bash scripts/install.sh
sudo /usr/local/sbin/openhands-postgres-manager status
sudo /usr/local/sbin/openhands-postgres-manager provision
sudo systemctl enable --now openhands-postgres-provision.timer
```

The installer does **not** automatically enable any timers, deploy PostgreSQL, modify existing agent containers, or turn on deletion. See [Operations](docs/OPERATIONS.md) for verification, recovery and rollback.

## Agent skill

Enable your existing `postgresql-integration-testing` OpenHands skill. It should load `/tmp/openhands-postgres.env` and map the `PG*` variables to the repository's test configuration. It must not use production databases, Docker commands, or the PostgreSQL superuser.

## Safety

Conversation containers can disappear when suspended; this is **not** proof of deletion. Cleanup checks an authenticated OpenHands conversation API, requires a live positive control, verifies no current or stopped runtime exists, and waits 24 hours after confirmed 404 before any eligible deletion. Due to unresolved API/lifecycle races, destructive cleanup remains opt-in and must be validated locally.

**Warning:** Existing databases from the earlier experimental provisioner are not automatically adopted or deleted.

Read [Security](docs/SECURITY.md) and [Operations](docs/OPERATIONS.md).

## Development

```bash
python3 -m py_compile openhands-postgres-manager
python3 -m unittest discover -s tests -v
bash -n scripts/*.sh
```

MIT licensed.
