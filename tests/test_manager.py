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
                m, "containers", return_value={"a"*64: ("agent-server-conversation-test", "00000000-0000-4000-8000-000000000001")}
            ), patch.object(m, "api_status", return_value=401), patch.object(m, "pg") as sql:
                m.cleanup({"a"*64: {"conversation": "00000000-0000-4000-8000-000000000001", "role": m.ident("a"*64)}}, apply=True)
                sql.assert_not_called()

    def test_cleanup_no_running_agent_never_deletes(self):
        with patch.object(m, "containers", return_value={}):
            with patch.object(m, "pg") as sql:
                m.cleanup({"a"*64: {"conversation": "dummy", "role": m.ident("a"*64)}}, apply=True)
                sql.assert_not_called()

if __name__ == "__main__":
    unittest.main()
