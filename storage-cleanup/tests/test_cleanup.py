import os
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from storage_cleanup import cleaner, locations, scanner


def make_file(path: Path, content: bytes, age_days: float = 0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    if age_days:
        old = time.time() - age_days * 86400
        os.utime(path, (old, old))
    return path


class SizeTests(unittest.TestCase):
    def test_parse_size(self):
        self.assertEqual(scanner.parse_size("2KB"), 2048)
        self.assertEqual(scanner.parse_size("1.5 MB"), int(1.5 * 1024**2))
        self.assertEqual(scanner.parse_size("100"), 100)

    def test_human_size(self):
        self.assertEqual(scanner.human_size(500), "500 B")
        self.assertEqual(scanner.human_size(1024**3), "1.0 GB")


class ScanAndCleanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_scan_respects_min_age_and_clean_deletes(self):
        old = make_file(self.root / "a" / "old.tmp", b"x" * 100, age_days=5)
        new = make_file(self.root / "new.tmp", b"y" * 50)
        with mock.patch.dict(locations.CATEGORIES, {"temp": ("Temp", lambda: [self.root])}):
            result = scanner.scan_category("temp", min_age_days=1)
        self.assertEqual([f.path for f in result.files], [old])

        preview = cleaner.delete_files(result.files, dry_run=True)
        self.assertEqual(preview.freed, 100)
        self.assertTrue(old.exists(), "dry run must not delete")

        report = cleaner.delete_files(result.files, dry_run=False)
        self.assertEqual(report.deleted, 1)
        self.assertFalse(old.exists())
        self.assertTrue(new.exists())

        self.assertEqual(cleaner.remove_empty_dirs([self.root], dry_run=False), 1)
        self.assertFalse((self.root / "a").exists())
        self.assertTrue(self.root.exists())

    def test_symlinks_are_not_followed(self):
        outside = TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        make_file(Path(outside.name) / "precious.txt", b"keep me", age_days=5)
        (self.root / "link").symlink_to(outside.name)
        self.assertEqual(list(scanner.walk_files([self.root])), [])

    def test_find_duplicates_keeps_oldest(self):
        original = make_file(self.root / "photo.jpg", b"same" * 500, age_days=10)
        copy = make_file(self.root / "backup" / "photo (1).jpg", b"same" * 500)
        make_file(self.root / "other.jpg", b"diff" * 500)
        groups = scanner.find_duplicates(self.root, min_size=1)
        self.assertEqual(len(groups), 1)
        self.assertEqual([e.path for e in groups[0]], [original, copy])

    def test_large_files(self):
        make_file(self.root / "big.bin", b"0" * 5000)
        make_file(self.root / "small.bin", b"0" * 10)
        found = scanner.find_large_files(self.root, min_size=1000)
        self.assertEqual([e.path.name for e in found], ["big.bin"])

    def test_protected_paths(self):
        self.assertTrue(cleaner.is_protected(Path("/etc/passwd")))
        self.assertTrue(cleaner.is_protected(Path.home()))
        self.assertFalse(cleaner.is_protected(self.root / "file.tmp"))


if __name__ == "__main__":
    unittest.main()
