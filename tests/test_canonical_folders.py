import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from canonical_folders import find_matter, is_under, validate_registry


class CanonicalFolderTests(unittest.TestCase):
    def test_valid_registry(self):
        with tempfile.TemporaryDirectory() as temp:
            root = str(Path(temp) / "matters")
            registry = {
                "schemaVersion": 1,
                "matters": [
                    {
                        "matterId": "synthetic-001",
                        "canonicalFolder": str(Path(root) / "demo-001"),
                        "folderAliases": [],
                    }
                ],
            }
            self.assertEqual(validate_registry(registry, [root]), [])
            self.assertTrue(is_under(str(Path(root) / "demo-001"), [root]))
            self.assertEqual(find_matter(registry, "synthetic-001")["matterId"], "synthetic-001")

    def test_detects_collision(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = str(Path(temp) / "same")
            registry = {
                "schemaVersion": 1,
                "matters": [
                    {"matterId": "one", "canonicalFolder": folder, "folderAliases": []},
                    {"matterId": "two", "canonicalFolder": folder, "folderAliases": []},
                ],
            }
            self.assertTrue(any("collision" in error for error in validate_registry(registry, [temp])))


if __name__ == "__main__":
    unittest.main()

