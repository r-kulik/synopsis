import unittest

from synopsis_domain.model import *
from synopsis_domain.service import CourseService, DomainError, ErrorCode
from synopsis_domain.url import make_internal_url, parse_internal_url


def make_service():
    course = Course(CourseId("course-a"), "Linear algebra")
    lecture = Note(NoteId("lecture"), course.id, NoteKind.LECTURE, "Vectors", "", "intro")
    concept = Note(NoteId("vector"), course.id, NoteKind.CONCEPT, "Vector", "", "A vector")
    external = Note(NoteId("cos"), course.id, NoteKind.EXTERNAL_CONCEPT, "Cosine", "", "")
    s = CourseService(CourseSnapshot(course, {lecture.id: lecture, concept.id: concept, external.id: external}))
    s.create_card(Card(CardId("vector-card"), course.id, concept.id, Point(10, 20)))
    s.create_card(Card(CardId("cos-card"), course.id, external.id, Point(30, 20)))
    return s


class ContractTests(unittest.TestCase):
    def test_url_round_trip_and_invalid_text_is_not_exception(self):
        self.assertEqual(parse_internal_url(make_internal_url("source", "s1", page=2)).page, 2)
        self.assertIsNone(parse_internal_url("synopsis://note/"))
        self.assertIsNone(parse_internal_url("synopsis://note/x?page=2"))

    def test_dangling_or_foreign_url_is_unresolved_without_markdown_mutation(self):
        s = make_service()
        original = "[Other](synopsis://note/course-b-note)"
        s.state.notes[NoteId("vector")].markdown = original
        self.assertIsNone(s.resolve_internal_url("synopsis://note/course-b-note"))
        self.assertEqual(s.state.notes[NoteId("vector")].markdown, original)

    def test_course_isolation_and_edge_matrix(self):
        s = make_service()
        with self.assertRaises(DomainError) as e: s.create_edge(Edge(EdgeId("bad"), CourseId("other"), EdgeKind.HIERARCHICAL, CardId("vector-card"), CardId("cos-card")))
        self.assertEqual(e.exception.code, ErrorCode.COURSE_MISMATCH)
        with self.assertRaises(DomainError): s.create_edge(Edge(EdgeId("bad2"), s.state.course.id, EdgeKind.HIERARCHICAL, CardId("vector-card"), CardId("cos-card")))

    def test_lecture_box_removal_keeps_note_cards_edges_and_world_position(self):
        s = make_service(); st = s.state
        st.lecture_boxes[LectureBoxId("box")] = LectureBox(LectureBoxId("box"), st.course.id, NoteId("lecture"), Point(0,0), Point(100,100))
        st.cards[CardId("vector-card")].lecture_box_id = LectureBoxId("box")
        before = st.cards[CardId("vector-card")].position; s.remove_lecture_box(LectureBoxId("box"))
        self.assertEqual(st.cards[CardId("vector-card")].position, before); self.assertIsNone(st.cards[CardId("vector-card")].lecture_box_id); self.assertIn(NoteId("lecture"), st.notes)

    def test_delete_note_preserves_other_markdown_and_cardless_note_is_valid(self):
        s = make_service(); st = s.state
        other = Note(NoteId("other"), st.course.id, NoteKind.EXAMPLE, "Other", "", "[Vector](synopsis://note/vector)")
        st.notes[other.id] = other; s.delete_note(NoteId("vector"))
        self.assertEqual(other.markdown, "[Vector](synopsis://note/vector)"); self.assertIn(other.id, st.notes)

    def test_selection_is_atomic_and_revision_aware(self):
        s = make_service(); st = s.state; st.notes[NoteId("vector")].markdown = "select this"
        note = Note(NoteId("new"), st.course.id, NoteKind.CONCEPT, "this", "", "")
        card = Card(CardId("new-card"), st.course.id, note.id, Point(1,1))
        s.create_note_from_selection(source_note_id=NoteId("vector"), expected_revision=0, raw_start=7, raw_end=11, note=note, card=card)
        self.assertIn("synopsis://note/new", st.notes[NoteId("vector")].markdown)
        with self.assertRaises(DomainError): s.save_markdown(NoteId("vector"), "stale", 0)

    def test_source_patch_only_changes_requested_range(self):
        s = make_service(); note = s.state.notes[NoteId("vector")]; note.markdown = "same same"
        s.apply_source_patch(note.id, 0, 5, 9, "[same](synopsis://note/new)")
        self.assertEqual(note.markdown, "same [same](synopsis://note/new)")

    def test_fact_has_exactly_one_owner(self):
        s = make_service(); fact = Fact(FactId("f"), s.state.course.id, NoteId("vector"), "comment")
        s.create_fact(fact); self.assertEqual(s.state.facts[fact.id].owner_note_id, NoteId("vector"))


if __name__ == "__main__": unittest.main(verbosity=2)
