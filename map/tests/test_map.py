from __future__ import annotations
import json
import unittest
from synopsis_domain import (Card, CardId, Course, CourseId, CourseSnapshot, EdgeKind,
                             LectureBox, LectureBoxId, Note, NoteId, NoteKind, Point)
from storage.file_storage import _snapshot_from_data, _snapshot_to_data
from map import CourseMap, MapCommands
from map_settings import MapSettings


def snapshot() -> CourseSnapshot:
    course = Course(CourseId("linear"), "Линейная алгебра")
    notes = {
        NoteId("vectors"): Note(NoteId("vectors"), course.id, NoteKind.LECTURE, "Векторы", "", ""),
        NoteId("matrices"): Note(NoteId("matrices"), course.id, NoteKind.LECTURE, "Матрицы", "", ""),
        NoteId("vector"): Note(NoteId("vector"), course.id, NoteKind.CONCEPT, "Вектор", "Элемент пространства", "# V"),
        NoteId("matrix"): Note(NoteId("matrix"), course.id, NoteKind.CONCEPT, "Матрица", "Таблица чисел", "# M"),
        NoteId("diagonal"): Note(NoteId("diagonal"), course.id, NoteKind.CONCEPT, "Диагональная", "Нули вне диагонали", ""),
        NoteId("external"): Note(NoteId("external"), course.id, NoteKind.EXTERNAL_CONCEPT, "Косинус", "Внешнее", ""),
        NoteId("example"): Note(NoteId("example"), course.id, NoteKind.EXAMPLE, "Пример", "Пример", ""),
        NoteId("task"): Note(NoteId("task"), course.id, NoteKind.TASK, "Задача", "Задача", ""),
        NoteId("cardless"): Note(NoteId("cardless"), course.id, NoteKind.CONCEPT, "Без карточки", "Свободная", ""),
    }
    a, b = LectureBoxId("a"), LectureBoxId("b")
    cards = {CardId("vector"): Card(CardId("vector"), course.id, NoteId("vector"), Point(100, 100), lecture_box_id=a),
             CardId("matrix"): Card(CardId("matrix"), course.id, NoteId("matrix"), Point(500, 100), lecture_box_id=b),
             CardId("diagonal"): Card(CardId("diagonal"), course.id, NoteId("diagonal"), Point(500, 220), lecture_box_id=b),
             CardId("external"): Card(CardId("external"), course.id, NoteId("external"), Point(800, 100)),
             CardId("example"): Card(CardId("example"), course.id, NoteId("example"), Point(800, 200)),
             CardId("task"): Card(CardId("task"), course.id, NoteId("task"), Point(800, 300))}
    return CourseSnapshot(course, notes, cards, {a: LectureBox(a, course.id, NoteId("vectors"), Point(40, 40), Point(350, 250)), b: LectureBox(b, course.id, NoteId("matrices"), Point(440, 40), Point(350, 300))})


class MapTests(unittest.TestCase):
    def setUp(self): self.state = snapshot(); self.commands = MapCommands(self.state)

    def test_root_boxes_cards_only_title_and_summary(self):
        view = CourseMap.from_snapshot(self.state)
        self.assertEqual("Линейная алгебра", view.root.title); self.assertEqual(2, len(view.lecture_boxes))
        card = next(x for x in view.cards if x.id == "vector")
        self.assertEqual(("Вектор", "Элемент пространства"), (card.title, card.summary))

    def test_edge_matrix_cross_lecture_and_cycles(self):
        self.commands.create_edge(edge_id="context", kind=EdgeKind.CONTEXTUAL, source_card_id="vector", target_card_id="matrix", label="матрица — группа векторов")
        self.commands.create_edge(edge_id="h1", kind=EdgeKind.HIERARCHICAL, source_card_id="matrix", target_card_id="diagonal")
        self.commands.create_edge(edge_id="h2", kind=EdgeKind.HIERARCHICAL, source_card_id="diagonal", target_card_id="matrix")
        with self.assertRaises(ValueError): self.commands.create_edge(edge_id="bad", kind=EdgeKind.HIERARCHICAL, source_card_id="external", target_card_id="vector")
        self.assertEqual("матрица — группа векторов", self.state.edges["context"].label)

    def test_special_edge_types_and_style_settings_persist(self):
        self.commands.create_edge(edge_id="mention", kind=EdgeKind.MENTION, source_card_id="external", target_card_id="vector")
        self.commands.create_edge(edge_id="example", kind=EdgeKind.EXAMPLE_ATTACHMENT, source_card_id="example", target_card_id="matrix")
        self.commands.create_edge(edge_id="task", kind=EdgeKind.TASK_ATTACHMENT, source_card_id="task", target_card_id="matrix")
        settings = MapSettings.from_course_settings(self.state.course.settings)
        settings.edge_styles["contextual"]["dash"] = "dotted"; settings.card_styles["concept"]["fill"] = "#ffeeaa"
        self.commands.set_settings(settings)
        restored = MapSettings.from_course_settings(self.state.course.settings)
        self.assertEqual("dotted", restored.edge_styles["contextual"]["dash"])
        self.assertEqual("#ffeeaa", restored.card_styles["concept"]["fill"])

    def test_relative_points_follow_endpoints_and_persist_restart(self):
        self.commands.create_edge(edge_id="context", kind=EdgeKind.CONTEXTUAL, source_card_id="vector", target_card_id="matrix")
        self.commands.set_control_point("context", 0, Point(350, 30)); before = CourseMap.from_snapshot(self.state).edges[0].path
        self.commands.move_card("vector", Point(20, 10)); moved = CourseMap.from_snapshot(self.state).edges[0].path
        self.assertNotEqual(before, moved)
        # This is the exact S02 snapshot serializer used on a later process restart.
        reloaded = _snapshot_from_data(json.loads(json.dumps(_snapshot_to_data(self.state))))
        self.assertEqual(moved, CourseMap.from_snapshot(reloaded).edges[0].path)

    def test_moving_box_moves_children_in_world_coordinates(self):
        before = self.state.cards[CardId("matrix")].position
        self.commands.move_lecture_box("b", Point(25, -10))
        self.assertEqual(Point(before.x + 25, before.y - 10), self.state.cards[CardId("matrix")].position)

    def test_filter_is_non_mutating_and_hides_incident_edges(self):
        self.commands.create_edge(edge_id="mention", kind=EdgeKind.MENTION, source_card_id="external", target_card_id="vector")
        settings = MapSettings.from_course_settings(self.state.course.settings); settings.hidden_note_kinds.add("externalConcept"); self.commands.set_settings(settings)
        view = CourseMap.from_snapshot(self.state)
        self.assertNotIn("external", [x.id for x in view.cards]); self.assertNotIn("mention", [x.id for x in view.edges])
        self.assertIn(CardId("external"), self.state.cards); self.assertIn("mention", self.state.edges)

    def test_remove_and_recreate_card_uses_public_domain_semantics(self):
        self.commands.create_edge(edge_id="context", kind=EdgeKind.CONTEXTUAL, source_card_id="vector", target_card_id="matrix")
        self.commands.remove_card("vector")
        self.assertIn(NoteId("vector"), self.state.notes); self.assertNotIn("context", self.state.edges)
        card = self.commands.recreate_card("vector", Point(900, 500), card_id="vector-new")
        self.assertEqual(Point(900, 500), card.position)

    def test_remove_box_preserves_children_edges_and_world_position(self):
        self.commands.create_edge(edge_id="context", kind=EdgeKind.CONTEXTUAL, source_card_id="vector", target_card_id="matrix")
        before = self.state.cards[CardId("matrix")].position; self.commands.remove_lecture_box("b")
        self.assertEqual(before, self.state.cards[CardId("matrix")].position); self.assertIsNone(self.state.cards[CardId("matrix")].lecture_box_id)
        self.assertIn("context", self.state.edges); self.assertIn(NoteId("matrices"), self.state.notes)

    def test_free_card_position_never_reflows_existing_cards(self):
        old = {key: card.position for key, card in self.state.cards.items()}
        self.commands.recreate_card("cardless", Point(1200, 900), card_id="new")
        self.assertEqual(old, {key: self.state.cards[key].position for key in old})


if __name__ == "__main__": unittest.main(verbosity=2)
