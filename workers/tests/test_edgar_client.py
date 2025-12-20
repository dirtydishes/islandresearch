import tempfile
import unittest
from pathlib import Path

from workers.edgar_client import StorageWriter


class StorageWriterTests(unittest.TestCase):
    def test_save_bytes_append_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = StorageWriter(root=tmpdir)
            first = Path(writer.save_bytes("0000000000", "acc-1", b"content", suffix="html"))
            second = Path(writer.save_bytes("0000000000", "acc-1", b"new-content", suffix="html"))

            self.assertTrue(first.exists())
            self.assertTrue(second.exists())
            self.assertNotEqual(first, second)
            self.assertEqual(first.read_bytes(), b"content")
            self.assertEqual(second.read_bytes(), b"new-content")

    def test_save_json_append_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = StorageWriter(root=tmpdir)
            first = Path(writer.save_json("0000000000", "submissions", {"value": 1}))
            second = Path(writer.save_json("0000000000", "submissions", {"value": 2}))

            self.assertTrue(first.exists())
            self.assertTrue(second.exists())
            self.assertNotEqual(first, second)
            self.assertIn("submissions", first.name)
            self.assertIn("submissions", second.name)
            self.assertNotEqual(first.read_text(), second.read_text())


if __name__ == "__main__":
    unittest.main()
