import importlib.util
import json
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("release", Path(__file__).resolve().parents[1] / "scripts/release.py")
r = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(r)


def pr(number=1, *labels):
    return {"number": number, "labels": [{"name": label} for label in labels]}


class ReleaseTests(unittest.TestCase):
    def test_patch_by_default(self):
        self.assertEqual(r.release_kind([pr()]), "patch")
        self.assertEqual(r.bump("v1.2.3", "patch"), "v1.2.4")

    def test_minor_and_major_reset_lower_components(self):
        self.assertEqual(r.bump("v1.2.3", "minor"), "v1.3.0")
        self.assertEqual(r.bump("v1.2.3", "major"), "v2.0.0")
        self.assertEqual(r.bump("v0.0.0", "major"), "v1.0.0")

    def test_highest_requested_bump(self):
        self.assertEqual(r.release_kind([pr(), pr(2, "release:minor"), pr(3, "release:major")]), "major")

    def test_skip_does_not_override_other_pull_requests(self):
        self.assertIsNone(r.release_kind([pr(1, "release:none")]))
        self.assertEqual(r.release_kind([pr(1, "release:none"), pr(2)]), "patch")

    def test_conflicting_labels_fail_closed(self):
        for labels in [("release:none", "release:major"), ("release:patch", "release:minor")]:
            with self.assertRaises(ValueError):
                r.release_kind([pr(1, *labels)])

    def test_unrelated_labels_do_not_change_default(self):
        self.assertEqual(r.release_kind([pr(1, "bug", "documentation")]), "patch")

    def test_invalid_versions_are_rejected(self):
        for version in ["v01.0.0", "1.0.0", "v1.0", "v1.0.0-rc1"]:
            with self.assertRaises(ValueError):
                r.bump(version, "patch")

    def test_updates_installed_executable_source_and_changelog(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "openhands-postgres-manager").write_text('__version__ = "0.1.0"\n')
            (root / "CHANGELOG.md").write_text("# Changelog\n\n## Unreleased\n")
            r.update_version(root, "v1.0.0", [1])
            self.assertIn('__version__ = "1.0.0"', (root / "openhands-postgres-manager").read_text())
            self.assertIn("## 1.0.0\n\nMerged pull requests: #1.", (root / "CHANGELOG.md").read_text())

    def test_stale_ci_run_does_not_publish(self):
        with patch.dict(r.os.environ, {"GH_REPO": "owner/repo", "SOURCE_SHA": "old"}), patch.object(r, "run", side_effect=["", "new", "", "ordinary merge"]), patch.object(r, "publish") as publish:
            r.main()
            publish.assert_not_called()

    def test_retry_reuses_atomically_pushed_tag(self):
        with patch.dict(r.os.environ, {"GH_REPO": "owner/repo", "SOURCE_SHA": "source"}), patch.object(r, "run", side_effect=["", "releasecommit", "", "chore: release v1.0.0\n\nRelease-Source: source", "source", "v1.0.0"]), patch.object(r, "publish") as publish:
            r.main()
            publish.assert_called_once_with("v1.0.0")

    def test_existing_release_is_not_recreated(self):
        with patch.object(r.subprocess, "run") as process, patch.object(r, "run") as run:
            process.return_value.returncode = 0
            r.publish("v1.0.0")
            run.assert_not_called()

    def test_real_git_release_push_and_retry_do_not_double_bump(self):
        original_run = r.run
        old_cwd = Path.cwd()
        with TemporaryDirectory() as temp:
            root = Path(temp)
            remote = root / "remote.git"
            work = root / "work"
            original_run("git", "init", "--bare", str(remote))
            original_run("git", "init", "-b", "main", str(work))
            try:
                os.chdir(work)
                original_run("git", "config", "user.name", "Test")
                original_run("git", "config", "user.email", "test@example.com")
                original_run("git", "remote", "add", "origin", str(remote))
                (work / "openhands-postgres-manager").write_text('__version__ = "0.1.0"\n')
                (work / "CHANGELOG.md").write_text("# Changelog\n\n## Unreleased\n")
                (work / "tests").mkdir()
                (work / "tests/test_smoke.py").write_text(
                    'import unittest\nfrom pathlib import Path\nclass Smoke(unittest.TestCase):\n'
                    ' def test_released_version(self):\n'
                    '  self.assertIn("1.0.0", Path("openhands-postgres-manager").read_text())\n'
                )
                original_run("git", "add", ".")
                original_run("git", "commit", "-m", "Merge PR 1")
                source = original_run("git", "rev-parse", "HEAD")
                original_run("git", "push", "origin", "main")
                pull = pr(1, "release:major")
                pull.update(merged_at="2026-11-13", base={"ref": "main"}, merge_commit_sha=source)

                def command(*args):
                    if args[:2] == ("gh", "api"):
                        return json.dumps([[pull]])
                    return original_run(*args)

                with patch.dict(r.os.environ, {"GH_REPO": "owner/repo", "SOURCE_SHA": source}), patch.object(r, "run", side_effect=command), patch.object(r, "publish") as publish:
                    r.main()
                    released = original_run("git", "rev-parse", "HEAD")
                    self.assertNotEqual(released, source)
                    self.assertEqual(original_run("git", "rev-parse", "v1.0.0"), released)
                    self.assertIn(released, original_run("git", "ls-remote", "origin", "refs/heads/main"))
                    r.main()
                    self.assertEqual(original_run("git", "rev-parse", "HEAD"), released)
                    self.assertEqual(publish.call_count, 2)
                    self.assertEqual(original_run("git", "tag"), "v1.0.0")
            finally:
                os.chdir(old_cwd)
