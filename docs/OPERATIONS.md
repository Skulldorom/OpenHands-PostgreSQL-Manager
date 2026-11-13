# Operations: runtime-scoped PostgreSQL databases

## Deployment

Run these commands as root **inside the OpenHands LXC**, not inside an agent container.

```bash
cd ~/OpenHands-PostgreSQL-Manager
systemctl stop openhands-postgres-reaper.timer
git pull --ff-only
python3 -m py_compile openhands-postgres-manager
python3 -m unittest discover -s tests -v
bash -n scripts/*.sh
bash scripts/install.sh
openhands-postgres-manager status
openhands-postgres-manager audit
openhands-postgres-manager provision
openhands-postgres-manager cleanup
systemctl status openhands-postgres-provision.timer --no-pager
```

The installed provisioning service stays active. The installer first runs syntax validation and the unit tests, then installs the executable and systemd units. No timer is enabled by the installer.

## Container lifecycle

- New Docker container, new `runtime:<container SHA256 ID>` state record and database `oh_<hash>`.
- Existing container, including stopped containers: database retained.
- Container removed by OpenHands: record initial absence on the first **applied** reaper run.
- If container is still absent after at least five minutes, the role and database are verified and dropped at most one per reaper run.
- Conversation resumed in a different container: newly provisioned, empty database. Do not expect earlier test data to survive.
- A new Docker container can arrive while an old one is being retired; the new runtime is independently provisioned.

The manager requires the authenticated persistent conversation API only to validate that a runtime belongs to OpenHands **during provisioning**. **Deletion does not depend on whether the persistent conversation exists**, only whether its original Docker container still exists.

## Migration from conversation-based manager

Previous state (`conv:<uuid>` or older container ID keys) is retained indefinitely for manual review. Their databases, roles, and credential files are **not automatically deleted** by the runtime cleanup job.

Existing live containers with `/tmp/openhands-postgres.env` from the old manager are not overwritten. They continue using their old database until OpenHands replaces them. A new runtime then receives its own dedicated database.

Run `openhands-postgres-manager audit` to see tracked, legacy, and untracked databases. Never manually delete a database without independently verifying ownership and that the contents are disposable.

## Confirm the complete lifecycle before enabling the reaper

1. Start a *new, disposable* OpenHands conversation and wait for the provisioning timer. Confirm `READY_RUNTIME` in its service logs.
2. Verify that the agent can authenticate to PostgreSQL using `/tmp/openhands-postgres.env`.
3. Stop the container without removing it and run `openhands-postgres-manager cleanup`. It must say `KEEP_RUNTIME`.
4. Remove **only that disposable container** through OpenHands, not with an indiscriminate Docker cleanup. Confirm `docker ps -a` no longer lists its immutable ID.
5. Run `openhands-postgres-manager cleanup` (read-only). It should say `ABSENT_FIRST_SEEN`; the clock is not saved on a dry run.
6. Back up the PostgreSQL volume and credential/state directory, then explicitly opt into the reaper after tests and the full lifecycle are verified:

```bash
systemctl enable --now openhands-postgres-events.service
systemctl enable --now openhands-postgres-reaper.timer
systemctl status openhands-postgres-reaper.timer --no-pager
journalctl -u openhands-postgres-reaper.service -n 40 --no-pager
```

The first applied run marks absence. At least five minutes later, a subsequent applied run can remove **one** eligible runtime database. Docker events trigger immediate provisioning and absence observation; the timer checks about every five minutes as fallback. Do not speed up or bypass the five-minute grace for production testing.

## Emergency stop

```bash
systemctl disable --now openhands-postgres-events.service
systemctl disable --now openhands-postgres-reaper.timer
systemctl stop openhands-postgres-reaper.service
```

This does not recover an already-deleted database. The reaper never touches PostgreSQL's shared service container or volume.

## Verification

```bash
openhands-postgres-manager status
openhands-postgres-manager audit
openhands-postgres-manager cleanup
systemctl list-timers '*openhands-postgres*'
journalctl -u openhands-postgres-provision.service -n 30 --no-pager
journalctl -u openhands-postgres-events.service -n 30 --no-pager
journalctl -u openhands-postgres-reaper.service -n 30 --no-pager
```

Never enable `cleanup --apply` outside the reaper unless deliberately recording absent runtimes. Existing legacy records require independent, manual reconciliation.

## Recovery

Back up `/opt/openhands-postgres` with permissions intact and the `openhands-postgres-data` Docker volume. The manager does not reset unknown PostgreSQL passwords or recreate dropped databases from a conversation transcript.

## Event-driven coupling

The `openhands-postgres-events.service` watches Docker `container start` and `container destroy` events for names matching `agent-server-conversation-<UUID>`. On start, it invokes the same locked provisioning command as the minute timer. On destroy, it immediately records first absence using the same guarded reaper logic. The reaper fallback runs every five minutes. The watcher automatically restarts when its Docker event stream ends.

A minimum **300-second** grace period separates first observed removal from deletion. Existing PostgreSQL connections, duplicate state references, invalid Docker state, and legacy records block removal. Cleanup remains opt-in via the reaper service. A Docker stop without removal is not a deletion event.

After installation, verify `systemctl status openhands-postgres-events.service` and inspect its journal for `WATCH_EVENT` messages. **Do not manually remove active OpenHands containers** just to test this behavior. Use a disposable OpenHands conversation and its normal lifecycle.
