import hashlib
import importlib.machinery
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader("manager", str(ROOT / "openhands-postgres-manager"))
spec = importlib.util.spec_from_loader(loader.name, loader)
m = importlib.util.module_from_spec(spec)
loader.exec_module(m)

class ManagerTests(unittest.TestCase):
    def test_id_is_deterministic_and_safe(self):
        cid = "a" * 64
        expected = "oh_" + hashlib.sha256(cid.encode()).hexdigest()[:16]
        self.assertEqual(m.ident(cid), expected)

    def test_invalid_container_id(self):
        for value in ("", "not-a-hash", "a" * 63, "A" * 64):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    m.ident(value)

    def test_identifier_sql_validation(self):
        self.assertEqual(m.sq("oh_example"), "'oh_example'")
        for value in ("x';DROP TABLE a;", "../data", "space here"):
            with self.assertRaises(ValueError):
                m.sq(value)

    def test_remote_credentials_missing_is_not_an_error(self):
        with patch.object(m.subprocess, "run") as proc:
            proc.return_value.returncode = 1
            self.assertFalse(m.remote_present("agent-server-conversation-test"))

    def test_remote_credentials_other_error_fails_closed(self):
        with patch.object(m.subprocess, "run") as proc:
            proc.return_value.returncode = 125
            with self.assertRaises(RuntimeError):
                m.remote_present("agent-server-conversation-test")

    def test_api_route_uses_actual_agent_server_prefix(self):
        self.assertEqual(
            m.API,
            "http://127.0.0.1:18000/api/conversations/",
        )

    def test_cleanup_auth_failure_does_not_delete(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as temp:
            key = Path(temp) / "key"
            key.write_text("example-test-key")
            with patch.object(m, "KEY", key), patch.object(
                m, "conversation_catalog", return_value={"00000000-0000-4000-8000-000000000001"}
            ), patch.object(m, "api_status", return_value=401), patch.object(
                m, "pg"
            ) as sql:
                m.cleanup({
                    "conv:00000000-0000-4000-8000-000000000002": {
                        "conversation": "00000000-0000-4000-8000-000000000002",
                        "role": "oh_aaaaaaaaaaaaaaaa",
                    }
                }, apply=True)
                sql.assert_not_called()

    def test_persistent_id_from_realistic_mount(self):
        persistent = "dfab8fcd-8e88-47cc-8a9f-2f5199e13322"
        info = {"Mounts": [
            {"Destination": "/workspace", "Source": "/root/workspace/project/dfab8fcd8e8847cc8a9f2f5199e13322"},
            {"Destination": "/var/openhands/conversations/dfab8fcd8e8847cc8a9f2f5199e13322",
             "Source": "/root/.openhands/agent-canvas/dev_conversations/dfab8fcd8e8847cc8a9f2f5199e13322"},
        ]}
        self.assertEqual(m.persistent_id_from_inspect(info), persistent)

    def test_mount_mapping_fails_closed(self):
        with self.assertRaises(RuntimeError):
            m.persistent_id_from_inspect({"Mounts": []})
        with self.assertRaises(RuntimeError):
            m.persistent_id_from_inspect({"Mounts": [{
                "Destination": "/var/openhands/conversations/dfab8fcd8e8847cc8a9f2f5199e13322",
                "Source": "/tmp/different",
            }]})

    def test_new_conversation_role_survives_container_recreation(self):
        conv = "dfab8fcd-8e88-47cc-8a9f-2f5199e13322"
        first, entry = m.record_for_conversation({}, conv, "a" * 64)
        second, after_resume = m.record_for_conversation({first: entry}, conv, "b" * 64)
        self.assertEqual(first, second)
        self.assertEqual(entry, after_resume)
        self.assertTrue(entry["credential_file"].startswith("conversation-"))

    def test_legacy_record_only_adopted_for_exact_current_runtime(self):
        conv = "dfab8fcd-8e88-47cc-8a9f-2f5199e13322"
        cid = "a" * 64
        old = {cid: {"conversation": "71ca7b40-c64e-48dd-b3b0-3fe0b3be33fa",
                     "role": m.ident(cid), "created_at": 123}}
        key, entry = m.record_for_conversation(old, conv, cid)
        self.assertEqual(key, "conv:" + conv)
        self.assertEqual(entry["role"], m.ident(cid))
        self.assertEqual(entry["credential_file"], cid + ".env")
        other_key, other_entry = m.record_for_conversation(old, conv, "b" * 64)
        self.assertNotEqual(other_entry["role"], m.ident(cid))

    def test_inventory_classifies_legacy_and_untracked_without_deleting(self):
        state = {
            "a" * 64: {"role": "oh_aaaaaaaaaaaaaaaa", "conversation": "runtime"},
            "conv:dfab8fcd-8e88-47cc-8a9f-2f5199e13322": {
                "role": "oh_bbbbbbbbbbbbbbbb",
                "conversation": "dfab8fcd-8e88-47cc-8a9f-2f5199e13322",
            },
        }
        db_rows = "\n".join(["oh_aaaaaaaaaaaaaaaa",
                             "oh_bbbbbbbbbbbbbbbb",
                             "oh_cccccccccccccccc"])
        from io import StringIO
        from contextlib import redirect_stdout
        with patch.object(m, "pg", return_value=db_rows) as sql, patch.object(
            m, "containers", return_value={}
        ), redirect_stdout(StringIO()) as output:
            m.audit(state)
        report = output.getvalue()
        self.assertIn("LEGACY_KEEP oh_aaaaaaaaaaaaaaaa", report)
        self.assertIn("TRACKED_KEEP oh_bbbbbbbbbbbbbbbb", report)
        self.assertIn("UNTRACKED_KEEP oh_cccccccccccccccc", report)
        self.assertIn("Audit is read-only", report)
        sql.assert_called_once()

    def test_inventory_missing_db_is_review_only(self):
        from io import StringIO
        from contextlib import redirect_stdout
        with patch.object(m, "pg", return_value=""), patch.object(
            m, "containers", return_value={}
        ), redirect_stdout(StringIO()) as output:
            m.audit({"a" * 64: {"role": "oh_aaaaaaaaaaaaaaaa"}})
        self.assertIn("MISSING_DB_REVIEW", output.getvalue())

    def test_cleanup_without_active_runtime_preserves_catalog_conversation(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as temp:
            key = Path(temp) / "key"
            key.write_text("example-test-key")
            conv = "00000000-0000-4000-8000-000000000001"
            with patch.object(m, "KEY", key), patch.object(
                m, "conversation_catalog", return_value={conv}
            ), patch.object(m, "api_status", return_value=200), patch.object(
                m, "containers", return_value={}
            ), patch.object(m, "pg") as sql:
                m.cleanup({"conv:" + conv: {
                    "conversation": conv, "role": "oh_aaaaaaaaaaaaaaaa",
                    "absent_since": None,
                }}, apply=True)
                sql.assert_not_called()

    def test_deleted_conversation_requires_first_observation(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as temp:
            key = Path(temp) / "key"
            key.write_text("example-test-key")
            live = "00000000-0000-4000-8000-000000000001"
            target = "00000000-0000-4000-8000-000000000002"
            state = {"conv:" + target: {
                "conversation": target, "role": "oh_aaaaaaaaaaaaaaaa",
                "absent_since": None,
            }}
            def api(conv, secret):
                return 200 if conv == live else 404
            with patch.object(m, "KEY", key), patch.object(
                m, "conversation_catalog", return_value={live}
            ), patch.object(m, "api_status", side_effect=api), patch.object(
                m, "containers", return_value={}
            ), patch.object(m, "pg") as sql, patch.object(m, "save_state") as saved:
                m.cleanup(state, apply=True)
                sql.assert_not_called()
                saved.assert_called_once()
                self.assertIsInstance(state["conv:" + target]["absent_since"], int)

    def test_cleanup_retains_legacy_records(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as temp:
            key = Path(temp) / "key"
            key.write_text("example-test-key")
            live = "00000000-0000-4000-8000-000000000001"
            with patch.object(m, "KEY", key), patch.object(
                m, "conversation_catalog", return_value={live}
            ), patch.object(m, "api_status", return_value=200), patch.object(
                m, "containers", return_value={}
            ), patch.object(m, "pg") as sql:
                m.cleanup({"a" * 64: {
                    "conversation": "temporary-runtime",
                    "role": "oh_aaaaaaaaaaaaaaaa",
                }}, apply=True)
                sql.assert_not_called()

    def test_cleanup_never_deletes_when_catalog_empty(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as temp:
            key = Path(temp) / "key"
            key.write_text("example-test-key")
            with patch.object(m, "KEY", key), patch.object(
                m, "conversation_catalog", return_value=set()
            ), patch.object(m, "pg") as sql:
                m.cleanup({"conv:00000000-0000-4000-8000-000000000002": {
                    "conversation": "00000000-0000-4000-8000-000000000002",
                    "role": "oh_aaaaaaaaaaaaaaaa",
                    "absent_since": 1
                }}, apply=True)
                sql.assert_not_called()

    def test_cleanup_observation_grace_never_drops_database(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as temp:
            key = Path(temp) / "key"
            key.write_text("example-test-key")
            live = "00000000-0000-4000-8000-000000000001"
            target = "00000000-0000-4000-8000-000000000002"
            def api(conv, secret):
                return 200 if conv == live else 404
            with patch.object(m, "KEY", key), patch.object(
                m, "conversation_catalog", return_value={live}
            ), patch.object(m, "api_status", side_effect=api), patch.object(
                m, "containers", return_value={}
            ), patch.object(m, "time") as tm, patch.object(m, "pg") as sql:
                tm.time.return_value = 10000
                m.cleanup({"conv:" + target: {
                    "conversation": target, "role": "oh_aaaaaaaaaaaaaaaa",
                    "absent_since": 9900
                }}, apply=True)
                sql.assert_not_called()

    def test_catalog_fails_on_duplicate_conversation(self):
        import io
        import json
        conv = "00000000-0000-4000-8000-000000000001"
        payload = {"items": [{"id": conv}, {"id": conv}], "next_page_id": None}
        class Response:
            status = 200
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, *args):
                return json.dumps(payload).encode()
        with patch.object(m.urllib.request, "urlopen", return_value=Response()):
            with self.assertRaises(RuntimeError):
                m.conversation_catalog("test-key")


    def test_runtime_key_is_distinct_from_conversation(self):
        cid = "a" * 64
        self.assertEqual(m.runtime_record_key(cid), "runtime:" + cid)

    def test_runtime_cleanup_preserves_stopped_container(self):
        from unittest.mock import MagicMock
        cid = "a" * 64
        role = m.ident(cid)
        state = {"runtime:" + cid: {
            "role": role, "credential_file": cid + ".env",
            "created_at": 100, "absent_since": None,
        }}
        with patch.object(m, "docker_snapshot", return_value={cid}), patch.object(
            m, "pg"
        ) as pg, patch.object(m, "save_state") as save:
            m.runtime_cleanup(state, apply=True)
            pg.assert_not_called()
            save.assert_not_called()

    def test_runtime_cleanup_starts_absence_clock(self):
        cid = "a" * 64
        state = {"runtime:" + cid: {
            "role": m.ident(cid), "credential_file": cid + ".env",
            "created_at": 100, "absent_since": None,
        }}
        with patch.object(m, "docker_snapshot", return_value=set()), patch.object(
            m.time, "time", return_value=1000
        ), patch.object(m, "save_state") as saved, patch.object(m, "pg") as pg:
            m.runtime_cleanup(state, apply=True)
            self.assertEqual(state["runtime:" + cid]["absent_since"], 1000)
            saved.assert_called_once()
            pg.assert_not_called()

    def test_runtime_cleanup_grace_period_prevents_drop(self):
        cid = "a" * 64
        state = {"runtime:" + cid: {
            "role": m.ident(cid), "credential_file": cid + ".env",
            "created_at": 100, "absent_since": 999,
        }}
        with patch.object(m, "docker_snapshot", return_value=set()), patch.object(
            m.time, "time", return_value=1000
        ), patch.object(m, "pg") as pg:
            m.runtime_cleanup(state, apply=True)
            pg.assert_not_called()

    def test_runtime_cleanup_protects_legacy_alias(self):
        cid = "a" * 64
        role = m.ident(cid)
        state = {
            "runtime:" + cid: {
                "role": role, "credential_file": cid + ".env",
                "created_at": 100, "absent_since": 1000,
            },
            cid: {"role": role, "conversation": "old-runtime"},
        }
        with patch.object(m, "docker_snapshot", return_value=set()), patch.object(
            m.time, "time", return_value=10000
        ), patch.object(m, "pg") as pg:
            m.runtime_cleanup(state, apply=True)
            pg.assert_not_called()

    def test_runtime_cleanup_never_touches_old_persistent_record(self):
        cid = "a" * 64
        state = {"conv:00000000-0000-4000-8000-000000000001": {
            "role": m.ident(cid), "credential_file": cid + ".env",
        }}
        with patch.object(m, "docker_snapshot", return_value=set()), patch.object(
            m, "pg"
        ) as pg:
            m.runtime_cleanup(state, apply=True)
            pg.assert_not_called()

    def test_runtime_cleanup_docker_failure_aborts(self):
        with patch.object(m, "docker_snapshot", side_effect=RuntimeError("offline")), patch.object(
            m, "pg"
        ) as pg:
            with self.assertRaises(RuntimeError):
                m.runtime_cleanup({}, apply=True)
            pg.assert_not_called()

    def test_runtime_provision_does_not_overwrite_existing_legacy_credentials(self):
        cid = "a" * 64
        with patch.object(m, "validated_conversation"), patch.object(
            m, "remote_present", return_value=True
        ), patch.object(m, "pg") as pg:
            m.runtime_provision(cid, "agent-server-conversation-test",
                                "00000000-0000-4000-8000-000000000001", {})
            pg.assert_not_called()


if __name__ == "__main__":
    unittest.main()
