# OpenHands PostgreSQL Manager

[![CI](https://github.com/Skulldorom/OpenHands-PostgreSQL-Manager/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Skulldorom/OpenHands-PostgreSQL-Manager/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-0.1.0-blue)](https://github.com/Skulldorom/OpenHands-PostgreSQL-Manager/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Ko-fi](https://img.shields.io/badge/Support%20on-Ko--fi-FF5E5B?logo=kofi&logoColor=white)](https://ko-fi.com/skulldorom)

Disposable PostgreSQL test databases for self-hosted OpenHands Agent Canvas conversation **Docker containers**.

## Lifecycle

1. OpenHands creates a runtime container.
2. Host-side provisioning creates a unique PostgreSQL database and restricted login keyed to the immutable full Docker container ID.
3. Agent runtime receives `/tmp/openhands-postgres.env` (mode 0600).
4. While the Docker container exists — including when stopped — its database is retained.
5. Once Docker no longer lists that container, the manager records the first observed absence.
6. After at least **five minutes** of continuous confirmed absence, the opt-in reaper may remove the database, login, and host-side credentials.
7. If an OpenHands conversation resumes in a **new** Docker container, it receives a **new empty database**.

The shared `openhands-postgres` PostgreSQL 17 server and Docker volume are never destroyed by the manager.

## Safety guarantees

- New runtime records use `runtime:<full Docker container ID>`. Older `conv:` and legacy records are **never automatically migrated or deleted**.
- Already-running containers with old PostgreSQL credentials are not overwritten.
- Missing Docker, failing state checks, mismatched role or password, database ownership uncertainty, existing PostgreSQL sessions, or duplicate state references blocks deletion.
- A stopped-but-existing Docker container is retained.
- Every deletion requires repeated Docker inspection and at least 300 seconds after first observed disappearance.
- The reaper deletes at most **one** database each run, and never automatically deletes untracked databases.
- The installer does not enable any systemd timers. The destructive reaper is separately opt-in.

## Setup on the OpenHands LXC

Prerequisites: Docker CLI on host, healthy `openhands-postgres` container, and PostgreSQL reachable at `172.17.0.1:55432` from agent containers.

```bash
cd ~/OpenHands-PostgreSQL-Manager
git pull --ff-only
python3 -m py_compile openhands-postgres-manager
python3 -m unittest discover -s tests -v
bash -n scripts/*.sh
bash scripts/install.sh
openhands-postgres-manager status
openhands-postgres-manager audit
openhands-postgres-manager provision
openhands-postgres-manager cleanup
```

After a disposable-runtime creation and removal test, enable the event watcher and fallback deletion timer:

```bash
systemctl enable --now openhands-postgres-events.service
systemctl enable --now openhands-postgres-reaper.timer
systemctl enable --now openhands-postgres-provision.timer
```

The event watcher reacts immediately to Docker `start` and `destroy` events. The provisioning timer runs every minute to recover missed start events; **it skips already-provisioned runtimes without executing commands inside them or re-reading credentials**. The reaper reconciles every five minutes. Deletion requires at least five minutes after the first observed Docker disappearance (longer if the watcher or timer misses it).

Read [Operations](docs/OPERATIONS.md) for safe rollout and validation. See [Security](docs/SECURITY.md). MIT licensed.

## Development and releases

CI runs the unit tests on Python 3.11–3.14 and checks Python syntax, every shell script, and whitespace. Tests use mocks; they do not require Docker or PostgreSQL and do not replace the disposable-runtime lifecycle validation described above.

Run the same checks locally:

```bash
python3 -m py_compile openhands-postgres-manager
python3 -m unittest discover -s tests -v
for script in scripts/*.sh; do bash -n "$script"; done
git diff --check
python3 openhands-postgres-manager --version
```

The executable's `__version__` is the runtime version source, also copied by the installer. `--version` works without root, Docker, or access to credentials.

Use semantic versioning: patch for fixes, minor for compatible features, major for breaking changes. Before a release, update `__version__`, the README version badge, and [CHANGELOG.md](CHANGELOG.md) in a reviewed PR. After merging, tag that commit and push the tag:

```bash
git switch main
git pull --ff-only
git tag v0.1.0
git push origin v0.1.0
```

Replace `v0.1.0` with the version being released. The release workflow runs the full CI matrix and verifies the tag matches `--version` before publishing GitHub release notes. A release does not update an installed host; installation remains explicit.

## Support

If this project is useful, you can [support my work on Ko-fi](https://ko-fi.com/skulldorom).
