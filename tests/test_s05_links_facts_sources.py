import unittest

from facts import attached_fact_ids, create_fact_from_selection, edit_fact, orphan_facts
from render import render_markdown
from selection import (FreeCardPlacement, SelectionError, create_note_from_selection,
                       find_notes_in_course, link_selection_to_note, selection_from_rendered)
from source_links import attach_pdf_to_lecture, external_open_intent, make_source_url
from synopsis_domain import (Asset, AssetId, Card, CardId, Course, CourseId, CourseService,
                             CourseSnapshot, DomainError, ErrorCode, Fact, FactId, Note,
                             NoteId, NoteKind, Point, Source, SourceId)


def service(raw="same same"):
    course = Course(CourseId("a"), "Course")
    source = Note(NoteId("source"), course.id, NoteKind.CONCEPT, "Source", "", raw)
    cardless = Note(NoteId("cardless"), course.id, NoteKind.EXAMPLE, "Cardless target", "", "")
    return CourseService(CourseSnapshot(course, {source.id: source, cardless.id: cardless}))


def select(s, start, end, text):
    note = s.state.notes[NoteId("source")]
    rendered = render_markdown(note.markdown, s.state)
    return selection_from_rendered(note_id=note.id, revision=note.revision, rendered=rendered,
                                   span_index=0, rendered_start=start, rendered_end=end, selected_text=text)


class S05Tests(unittest.TestCase):
    def test_exact_duplicate_phrase_patch_and_cardless_course_lookup(self):
        s = service()
        self.assertEqual([str(n.id) for n in find_notes_in_course(s, "target")], ["cardless"])
        link_selection_to_note(s, select(s, 5, 9, "same"), NoteId("cardless"))
        self.assertEqual(s.state.notes[NoteId("source")].markdown, "same [same](synopsis://note/cardless)")
        self.assertEqual(s.state.edges, {})

    def test_stale_or_unsupported_selection_never_writes(self):
        s = service("plain $x$ text")
        with self.assertRaises(SelectionError):
            selection_from_rendered(note_id=NoteId("source"), revision=0, rendered=render_markdown("plain $x$ text", s.state),
                                    span_index=0, rendered_start=0, rendered_end=1, selected_text="p")
        before = s.state.notes[NoteId("source")].markdown
        # Use a request from revision 0 after an independent save to model a stale read.
        s2 = service("same") ; request = select(s2, 0, 4, "same"); s2.save_markdown(NoteId("source"), "new", 0)
        with self.assertRaises(DomainError) as ctx: link_selection_to_note(s2, request, NoteId("cardless"))
        self.assertEqual(ctx.exception.code, ErrorCode.REVISION_CONFLICT)
        self.assertEqual(s2.state.notes[NoteId("source")].markdown, "new")
        self.assertEqual(s.state.notes[NoteId("source")].markdown, before)

    def test_create_note_is_atomic_visible_and_has_no_generated_edge(self):
        s = service("make")
        note = Note(NoteId("new"), s.state.course.id, NoteKind.CONCEPT, "make", "", "")
        card = Card(CardId("new-card"), s.state.course.id, note.id, Point(7, 8))
        create_note_from_selection(s, select(s, 0, 4, "make"), note, card, FreeCardPlacement(7, 8))
        self.assertIn(NoteId("new"), s.state.notes); self.assertEqual(s.state.edges, {})
        bad = service("make")
        with self.assertRaises(SelectionError): create_note_from_selection(bad, select(bad, 0, 4, "make"), note, card, FreeCardPlacement(1, 2))
        self.assertNotIn(NoteId("new"), bad.state.notes)

    def test_fact_owner_marker_edit_and_orphan_lifecycle(self):
        s = service("mark")
        fact = Fact(FactId("f"), s.state.course.id, NoteId("source"), "hidden")
        create_fact_from_selection(s, select(s, 0, 4, "mark"), fact)
        self.assertEqual(attached_fact_ids(s, NoteId("source")), {FactId("f")})
        edit_fact(s, FactId("f"), NoteId("source"), "edited")
        s.save_markdown(NoteId("source"), "marker removed", 1)
        self.assertEqual([f.id for f in orphan_facts(s, NoteId("source"))], [FactId("f")])
        other = Note(NoteId("other"), s.state.course.id, NoteKind.CONCEPT, "O", "", "[x](synopsis://fact/f)")
        s.state.notes[other.id] = other
        self.assertEqual(attached_fact_ids(s, other.id), set())
        with self.assertRaises(DomainError): edit_fact(s, FactId("f"), other.id, "no")

    def test_pdf_page_validation_and_external_intent(self):
        s = service(); c = s.state.course.id
        lecture = Note(NoteId("lecture"), c, NoteKind.LECTURE, "L", "", "")
        s.state.notes[lecture.id] = lecture
        asset = Asset(AssetId("pdf"), c, "application/pdf", "pdf", "lecture.pdf", 1)
        s.state.assets[asset.id] = asset
        source = Source(SourceId("src"), c, "Lecture", asset.id, 3); s.state.sources[source.id] = source
        self.assertEqual(make_source_url(s, source.id, 2), "synopsis://source/src?page=2")
        intent = external_open_intent(s, source.id, 2)
        self.assertFalse(intent.embedded); self.assertEqual(intent.target, "_blank"); self.assertTrue(intent.url.endswith("#page=2"))
        self.assertEqual(attach_pdf_to_lecture(s, lecture.id, source.id, 2).page, 2)
        with self.assertRaises(DomainError): make_source_url(s, source.id, 4)
        s.state.assets[asset.id].media_type = "image/png"
        with self.assertRaises(DomainError): external_open_intent(s, source.id)


if __name__ == "__main__": unittest.main(verbosity=2)
