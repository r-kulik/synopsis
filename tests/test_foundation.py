import unittest
from pathlib import Path
from unittest.mock import patch
from server.application import SynopsisApplication
from storage import FileCourseStorage, StorageWriteError

class FoundationTests(unittest.TestCase):
    # The Windows execution sandbox denies child access to tempfile-created ACLs.
    # This pre-created, ignored root is also a faithful local-storage test location.
    def setUp(self): self.storage = FileCourseStorage(Path.cwd() / "_storage_smoke"); self.app = SynopsisApplication(self.storage)
    def test_restart_persists_course_note_and_cardless_catalog(self):
        course = self.app.create_course("Linear algebra")
        note = self.app.create_note(course.id, kind="concept", title="Matrix", summary="array", markdown="# Matrix")
        self.app.create_lecture(course.id, "Lecture one")
        restarted = SynopsisApplication(FileCourseStorage(Path.cwd() / "_storage_smoke"))
        snapshot = restarted.snapshot(course.id)
        self.assertEqual(snapshot.course.title, "Linear algebra")
        self.assertEqual(snapshot.notes[note.id].markdown, "# Matrix")
        self.assertFalse(snapshot.cards)
    def test_failed_replace_preserves_last_saved_snapshot(self):
        course = self.app.create_course("Before")
        original = self.storage._course_path(course.id).read_bytes()
        with patch("storage.file_storage.os.replace", side_effect=OSError("disk failure")):
            with self.assertRaises(StorageWriteError): self.app.create_note(course.id, kind="concept", title="Lost")
        self.assertEqual(self.storage._course_path(course.id).read_bytes(), original)
        self.assertEqual(self.storage.load(course.id).notes, {})
    def test_asset_is_course_scoped(self):
        first = self.app.create_course("A"); second = self.app.create_course("B")
        asset = self.app.import_asset(first.id, "page.pdf", "application/pdf", b"%PDF bytes")
        self.assertEqual(self.storage.get_asset(first.id, asset.id)[1], b"%PDF bytes")
        with self.assertRaises(Exception): self.storage.get_asset(second.id, asset.id)
