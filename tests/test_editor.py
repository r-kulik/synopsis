import unittest
from editor import DraftTabs
from render import render_markdown
from synopsis_domain import Course, CourseId, CourseSnapshot, Note, NoteId, NoteKind, Asset, AssetId

class Saved: revision=3
class EditorTests(unittest.TestCase):
    def setUp(self):
        self.snapshot=CourseSnapshot(Course(CourseId("course"), "C"))
        self.snapshot.notes[NoteId("n")]=Note(NoteId("n"), CourseId("course"), NoteKind.CONCEPT, "N", "", "")
        self.snapshot.assets[AssetId("a")]=Asset(AssetId("a"), CourseId("course"), "image/png", "a", "a.png", 1)
    def test_raw_round_trip_and_tab_draft(self):
        tabs=DraftTabs(); tabs.open("n", "**Привет** 🚀", 2); tabs.edit("n", "**Привет** 🚀\n$x^2$")
        self.assertEqual(tabs.open("n", "stale", 99).text, "**Привет** 🚀\n$x^2$")
        saved=tabs.save("n", lambda nid, raw, rev: Saved())
        self.assertEqual(saved.revision, 3); self.assertFalse(tabs.open("n", "", 3).dirty)
    def test_asset_invalid_urls_and_formula_are_readable(self):
        result=render_markdown('![ok](synopsis://asset/a) ![x](C:\\x.png) ![r](https://x/a.png) [gone](synopsis://note/no) $\\write18{x}$', self.snapshot)
        self.assertIn('/api/courses/course/assets/a', result.html)
        self.assertIn('invalid-link', result.html); self.assertIn('formula-error', result.html)
        self.assertEqual({d.code for d in result.diagnostics}, {'localImagePath','remoteImage','invalidInternalUrl','invalidFormula'})
    def test_source_map_is_explicitly_bounded(self):
        result=render_markdown('plain Unicode ё\n$x$', self.snapshot)
        self.assertEqual(result.spans[0].rendered_text, 'plain Unicode ё')
        self.assertEqual(len(result.spans), 1)
