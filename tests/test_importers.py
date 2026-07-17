import json
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from import_lexdoctor_csv import build_preview, load_mapping
from import_pjn_event import normalize_event
from inventory_folders import inventory


class ImporterTests(unittest.TestCase):
    def test_lexdoctor_synthetic_fixture(self):
        mapping = load_mapping(ROOT / "config" / "lexdoctor-field-map.example.json")
        preview = build_preview(ROOT / "tests" / "fixtures" / "lexdoctor.synthetic.csv", mapping)
        self.assertTrue(preview["dryRun"])
        self.assertEqual(len(preview["records"]), 2)
        self.assertEqual(preview["issues"], [])
        self.assertEqual(preview["records"][0]["externalId"], "SYN-001")

    def test_pjn_event_is_staged_and_fingerprinted(self):
        source = json.loads(
            (ROOT / "integrations" / "pjn" / "pjn-event.example.json").read_text(encoding="utf-8")
        )
        event = normalize_event(source)
        self.assertEqual(event["reviewStatus"], "pending")
        self.assertEqual(len(event["fingerprint"]), 64)

    def test_folder_inventory_is_relative_and_bounded(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "client-a" / "matter-a" / "too-deep").mkdir(parents=True)
            records = inventory(root, 2)
            paths = {record["relativePath"] for record in records}
            self.assertIn("client-a", paths)
            self.assertIn("client-a/matter-a", paths)
            self.assertNotIn("client-a/matter-a/too-deep", paths)


if __name__ == "__main__":
    unittest.main()
