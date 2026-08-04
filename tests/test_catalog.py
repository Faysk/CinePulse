from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from cinepulse.component_manager import _safe_extract_zip, load_catalog


class CatalogTests(unittest.TestCase):
    def test_catalog_is_readable_and_unique(self) -> None:
        components = load_catalog()
        keys = [component.key for component in components]
        self.assertTrue(keys)
        self.assertEqual(len(keys), len(set(keys)))

    def test_zip_path_traversal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "unsafe.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("../escape.txt", "blocked")
            with self.assertRaises(ValueError):
                _safe_extract_zip(archive, root / "output")
            self.assertFalse((root / "escape.txt").exists())


if __name__ == "__main__":
    unittest.main()

