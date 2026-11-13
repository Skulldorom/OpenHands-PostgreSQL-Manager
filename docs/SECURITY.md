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

Automated destructive deletion is **disabled by default**. The installed cleanup systemd unit is dry-run only. Executing `cleanup --apply` additionally requires an explicit `OH_PG_ENABLE_DELETION=I_UNDERSTAND` environment setting.

Deletion requires an authenticated API 200 for a current running conversation, then an API 404 for the target, no Docker container (running or stopped) for that conversation, and 24 hours of confirmed absence with a final recheck. This reduces risk, but cannot eliminate races with an external agent runtime or a broken API/catalog. Validate the actual local API behavior before opting in.

Do not automatically switch the cleanup service to `--apply` without end-to-end tests and backups.
