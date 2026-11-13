#!/usr/bin/env python3
"""Release tested main commits. Invoked only by the release workflow."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

VERSION = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def bump(version, kind):
    match = VERSION.fullmatch(version)
    if not match:
        raise ValueError("Invalid stable version tag")
    major, minor, patch = map(int, match.groups())
    if kind == "major":
        return f"v{major + 1}.0.0"
    if kind == "minor":
        return f"v{major}.{minor + 1}.0"
    if kind == "patch":
        return f"v{major}.{minor}.{patch + 1}"
    raise ValueError("Unknown release kind")


def release_kind(pulls):
    kinds = []
    for pr in pulls:
        labels = {label["name"] for label in pr["labels"]}
        selected = labels & {"release:major", "release:minor", "release:patch", "release:none"}
        if len(selected) > 1:
            raise ValueError(f"Conflicting release labels on PR #{pr['number']}")
        kind = next(iter(selected), "release:patch").split(":")[1]
        if kind != "none":
            kinds.append(kind)
    return max(kinds, key={"patch": 0, "minor": 1, "major": 2}.get) if kinds else None


def update_version(root, version, numbers):
    path = root / "openhands-postgres-manager"
    text, count = re.subn(r'^__version__ = "[^"]+"$', f'__version__ = "{version[1:]}"', path.read_text(), flags=re.M)
    if count != 1:
        raise ValueError("Expected exactly one executable version")
    path.write_text(text)
    changelog = root / "CHANGELOG.md"
    entry = f"## {version[1:]}\n\nMerged pull requests: " + ", ".join(f"#{n}" for n in numbers) + ".\n\n"
    changelog.write_text(changelog.read_text().replace("# Changelog\n\n", "# Changelog\n\n" + entry, 1))


def publish(tag):
    # A published tag is immutable. Retrying release creation never bumps again.
    existing = subprocess.run(["gh", "release", "view", tag], capture_output=True)
    if existing.returncode:
        run("gh", "release", "create", tag, "--verify-tag", "--generate-notes", "--title", tag)


def main():
    repo = os.environ["GH_REPO"]
    source = os.environ["SOURCE_SHA"]
    run("git", "fetch", "origin", "main", "--tags")
    head = run("git", "rev-parse", "origin/main")
    run("git", "checkout", "--detach", head)
    message = run("git", "log", "-1", "--format=%B")
    if head != source:
        # Resume after an atomic push succeeded but GitHub release creation failed.
        if f"Release-Source: {source}" in message.splitlines() and run("git", "rev-parse", "HEAD^") == source:
            tags = [tag for tag in run("git", "tag", "--points-at", "HEAD").splitlines() if VERSION.fullmatch(tag)]
            if len(tags) != 1:
                raise ValueError("Expected one release tag for recovery")
            publish(tags[0])
        else:
            print("Newer main commit exists; its successful CI run will reconcile releases")
        return
    tags = [tag for tag in run("git", "tag", "--merged", "HEAD").splitlines() if VERSION.fullmatch(tag)]
    previous = max(tags, key=lambda tag: tuple(map(int, VERSION.fullmatch(tag).groups()))) if tags else None
    commits = run("git", "rev-list", "--first-parent", f"{previous}..HEAD" if previous else "HEAD").splitlines()
    pulls = {}
    for sha in commits:
        pages = json.loads(run("gh", "api", "--paginate", "--slurp", f"repos/{repo}/commits/{sha}/pulls?per_page=100"))
        for page in pages:
            for pr in page:
                if pr.get("merged_at") and pr["base"]["ref"] == "main" and pr.get("merge_commit_sha") in commits:
                    pulls[pr["number"]] = pr
    if not pulls:
        print("No unreleased merged pull requests")
        return
    kind = release_kind(pulls.values())
    if kind is None:
        print("All unreleased pull requests opt out of releases")
        return
    version = bump(previous or "v0.0.0", kind)
    if version in run("git", "tag").splitlines():
        raise ValueError("Target tag already exists outside main ancestry")
    numbers = sorted(pulls)
    update_version(Path.cwd(), version, numbers)
    run(sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q")
    run("git", "diff", "--check")
    run("git", "config", "user.name", "github-actions[bot]")
    run("git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    run("git", "add", "openhands-postgres-manager", "CHANGELOG.md")
    run("git", "commit", "-m", f"chore: release {version}\n\nRelease-Source: {source}")
    run("git", "tag", version)
    # If another merge wins the race, neither the commit nor tag is pushed.
    run("git", "push", "--atomic", "origin", "HEAD:refs/heads/main", f"refs/tags/{version}")
    publish(version)


if __name__ == "__main__":
    main()
