from __future__ import annotations

import io
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import pjn_expediente_sync as sync  # noqa: E402
import pjn_local_paths as local_paths  # noqa: E402
import pjn_resolve_expediente_ids as resolver  # noqa: E402


class FakeAuth:
    can_refresh = True

    def __init__(self) -> None:
        self.token = "first"
        self.refreshes = 0

    def current(self) -> str:
        return self.token

    def refresh(self) -> str:
        self.refreshes += 1
        self.token = "second"
        return self.token


class FakeResponse:
    def __init__(self, body: bytes, content_type: str) -> None:
        self.body = body
        self.headers = {"Content-Type": content_type}

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class AuthResilienceTests(unittest.TestCase):
    def test_notification_read_endpoint_is_blocked(self) -> None:
        with self.assertRaises(SystemExit):
            sync.ensure_safe_url("https://notif.pjn.gov.ar/api/notificaciones/123/leida")

    def test_sync_defaults_to_dry_run(self) -> None:
        with patch.object(sys, "argv", ["pjn_expediente_sync.py", "--matter-id", "matter-demo"]):
            args = sync.parse_args()
        self.assertTrue(args.dry_run)

    def test_resolver_defaults_to_dry_run(self) -> None:
        with patch.object(sys, "argv", ["pjn_resolve_expediente_ids.py"]):
            args = resolver.parse_args()
        self.assertTrue(args.dry_run)

    def test_request_refreshes_once_after_401(self) -> None:
        auth = FakeAuth()
        unauthorized = HTTPError(
            "https://notif.pjn.gov.ar/api/expedientes",
            401,
            "unauthorized",
            {},
            io.BytesIO(b'{"message":"expired"}'),
        )
        success = FakeResponse(b"[]", "application/json")
        with patch.object(sync, "urlopen", side_effect=[unauthorized, success]) as mocked:
            body, content_type = sync.request(auth, "https://notif.pjn.gov.ar/api/expedientes")
        self.assertEqual(body, b"[]")
        self.assertEqual(content_type, "application/json")
        self.assertEqual(auth.refreshes, 1)
        self.assertEqual(mocked.call_count, 2)

    def test_local_state_override_stays_outside_workspace(self) -> None:
        expected = Path("C:/temporary/pjn-local")
        with patch.dict(os.environ, {"PJN_LOCAL_STATE_DIR": str(expected)}):
            self.assertEqual(local_paths.local_state_dir(), expected)
            self.assertEqual(local_paths.token_cache_file(), expected / "pjn-token-cache.json")
            self.assertEqual(local_paths.node_tools_dir(), expected / "node-tools")
            self.assertEqual(local_paths.runs_dir(), expected / "runs")
            self.assertEqual(local_paths.logs_dir(), expected / "logs")

    def test_relative_canonical_folder_is_workspace_relative(self) -> None:
        configured = {"canonicalFolder": "data/matters/demo"}
        self.assertEqual(
            sync.canonical_folder_path(configured),
            sync.vault_root() / "data/matters/demo",
        )

    def test_staff_report_keeps_document_error_visible(self) -> None:
        report = {
            "matterId": "CIV-1-2026",
            "expediente": "CIV 1/2026",
            "downloaded": 0,
            "downloadedItems": [],
            "backfilledPublished": 0,
            "errors": 1,
        }
        rendered = sync.staff_report([report], sync.datetime(2026, 7, 17, 9, 30))
        self.assertIn("Errores: 1", rendered)
        self.assertIn("CIV-1-2026", rendered)


if __name__ == "__main__":
    unittest.main()
