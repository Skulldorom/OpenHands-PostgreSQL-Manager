# Security model

The manager runs **only on the trusted OpenHands LXC host** with access to Docker and the PostgreSQL administrator account via `docker exec`. Agent containers have no Docker socket, no added Linux capabilities, and receive only scoped PostgreSQL credentials via a mode-0600 file.

## Isolation and limitations

- Per-runtime databases and roles are distinct. The manager revokes `PUBLIC` access to each managed database.
- PostgreSQL role/database isolation is not a security boundary against resource-exhaustion SQL. Apply CPU, memory and connection limits and avoid sensitive data.
- The agent is root *inside its container*, so its own credentials are readable by that agent. This is intentional.
- Secrets never belong in source control, logs, PRs, or example output.
- Docker's default bridge allows other containers to reach the bridge listener. Database authentication is essential.
- An agent may resume in a *new* runtime and receive a new empty database.
- Host access, Docker daemon privileges, or superuser credentials must never be passed to an agent.

## Cleanup safety

The watcher listens for Docker container `start` and `destroy` events with the OpenHands runtime naming convention; it never deletes database resources by itself. Events invoke the existing host-side manager through the shared `flock` lock. If a Docker stream disconnects, systemd restarts the watcher, and the provisioning/reaper timers reconcile missed events.

Only records created under `runtime:<full container ID>` are eligible for automatic deletion. Old persistent-conversation, pre-migration, and untracked databases are not automatically removed. The host-side reaper requires an explicit deletion environment gate; the installer enables neither the watcher nor the reaper.

Deletion requires at least 300 seconds after the first confirmed container absence, repeated successful Docker daemon inspections, matching restricted role/database ownership, no other state aliases, safe host-side credential files, and zero active database sessions. No more than one database is deleted per reaper invocation. A stopped container that is still listed by Docker is retained.

This is disposable **test** infrastructure: once an eligible runtime database is deleted, the previous database contents cannot be recovered without backup. Keep the shared PostgreSQL server and its Docker volume protected, and validate a disposable container lifecycle before enabling the event watcher and reaper.
