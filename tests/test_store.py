import tempfile
import unittest
from pathlib import Path

from app.store import Store


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "test.db")

    def tearDown(self):
        self.temp.cleanup()

    def test_clip_lifecycle_and_search(self):
        clip = self.store.add_clip({"content": "A useful research note", "tags": ["research"]})
        self.assertEqual([clip["id"]], [item["id"] for item in self.store.clips("useful")])
        updated = self.store.update_clip(clip["id"], {"pinned": True, "archived": True})
        self.assertTrue(updated["pinned"])
        self.assertEqual(1, len(self.store.clips(archived=True)))
        self.assertTrue(self.store.delete_clip(clip["id"]))

    def test_combine_preserves_requested_order(self):
        first = self.store.add_clip({"content": "first"})
        second = self.store.add_clip({"content": "second"})
        self.assertEqual("- second\n- first", self.store.combine([second["id"], first["id"]], "bullets"))

    def test_rejects_empty_content(self):
        with self.assertRaisesRegex(ValueError, "content is required"):
            self.store.add_clip({"content": " "})


if __name__ == "__main__":
    unittest.main()
