# Changelog

## 1.0.0

Merged pull requests: #1.

## Unreleased

Initial development baseline of the existing manager, with test automation and release tooling.

- Isolated databases and restricted logins per immutable Docker runtime ID.
- Docker event watcher and lightweight provisioning reconciliation.
- Opt-in cleanup after five minutes of confirmed runtime absence, with deletion safeguards.
- Python 3.11–3.14 CI, label-driven automatic GitHub releases, and a root-free `--version` command.
- Ko-fi support link and repository funding configuration.
