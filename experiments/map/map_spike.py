"""S00-B map feasibility spike.  Standard-library only; not production UI code."""

from __future__ import annotations

import json
import unittest
from dataclasses import asdict, dataclass, field
from typing import Literal

Point = tuple[float, float]
CardType = Literal["concept", "externalConcept", "example", "task"]
EdgeKind = Literal["contextual", "hierarchical", "mention", "exampleAttachment", "taskAttachment"]


@dataclass
class LectureBox:
    id: str
    title: str
    position: Point
    size: Point


@dataclass
class Card:
    id: str
    note_kind: CardType
    title: str
    summary: str
    position: Point
    size: Point = (160, 72)
    lecture_box_id: str | None = None

    def centre(self) -> Point:
        return (self.position[0] + self.size[0] / 2, self.position[1] + self.size[1] / 2)


@dataclass
class RelativeControlPoint:
    # p = source + u*(target-source) + v*perpendicular(target-source)
    u: float
    v: float


@dataclass
class Edge:
    id: str
    kind: EdgeKind
    source_card_id: str
    target_card_id: str
    label: str | None = None
    control_points: list[RelativeControlPoint] = field(default_factory=list)


@dataclass
class CourseMap:
    course_id: str
    lecture_boxes: dict[str, LectureBox]
    cards: dict[str, Card]
    edges: dict[str, Edge]
    hidden_card_types: set[str] = field(default_factory=set)

    def assert_edge_is_allowed(self, edge: Edge) -> None:
        source, target = self.cards[edge.source_card_id], self.cards[edge.target_card_id]
        expected = {
            "contextual": ({"concept"}, {"concept"}),
            "hierarchical": ({"concept"}, {"concept"}),
            "mention": ({"externalConcept"}, {"concept"}),
            "exampleAttachment": ({"example"}, {"concept"}),
            "taskAttachment": ({"task"}, {"concept"}),
        }[edge.kind]
        if source.note_kind not in expected[0] or target.note_kind not in expected[1]:
            raise ValueError(f"{edge.kind} has incompatible endpoint kinds")

    def add_edge(self, edge: Edge) -> None:
        self.assert_edge_is_allowed(edge)  # Deliberately does not reject hierarchy cycles.
        self.edges[edge.id] = edge

    def endpoints(self, edge: Edge) -> tuple[Point, Point]:
        return self.cards[edge.source_card_id].centre(), self.cards[edge.target_card_id].centre()

    def set_control_point_from_world(self, edge_id: str, index: int, point: Point) -> None:
        edge = self.edges[edge_id]
        source, target = self.endpoints(edge)
        dx, dy = target[0] - source[0], target[1] - source[1]
        length_sq = dx * dx + dy * dy
        if length_sq == 0:
            raise ValueError("cannot place relative control point on coincident endpoints")
        px, py = point[0] - source[0], point[1] - source[1]
        # Projection on direction gives u.  Projection on its left normal gives v.
        relative = RelativeControlPoint((px * dx + py * dy) / length_sq,
                                        (px * -dy + py * dx) / length_sq)
        if index == len(edge.control_points):
            edge.control_points.append(relative)
        else:
            edge.control_points[index] = relative

    def path(self, edge_id: str) -> list[Point]:
        edge = self.edges[edge_id]
        source, target = self.endpoints(edge)
        dx, dy = target[0] - source[0], target[1] - source[1]
        middle = [(source[0] + cp.u * dx - cp.v * dy,
                   source[1] + cp.u * dy + cp.v * dx) for cp in edge.control_points]
        return [source, *middle, target]

    def move_card(self, card_id: str, delta: Point) -> None:
        card = self.cards[card_id]
        card.position = (card.position[0] + delta[0], card.position[1] + delta[1])

    def move_lecture_box(self, box_id: str, delta: Point) -> None:
        box = self.lecture_boxes[box_id]
        box.position = (box.position[0] + delta[0], box.position[1] + delta[1])
        for card in self.cards.values():
            if card.lecture_box_id == box_id:
                self.move_card(card.id, delta)

    def visible(self) -> tuple[set[str], set[str]]:
        cards = {card_id for card_id, card in self.cards.items()
                 if card.note_kind not in self.hidden_card_types}
        # Visibility never mutates the graph; an edge is hidden when either endpoint is hidden.
        edges = {edge_id for edge_id, edge in self.edges.items()
                 if edge.source_card_id in cards and edge.target_card_id in cards}
        return cards, edges

    def to_json(self) -> str:
        value = asdict(self)
        value["hidden_card_types"] = sorted(self.hidden_card_types)
        return json.dumps(value, sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, raw: str) -> "CourseMap":
        value = json.loads(raw)
        boxes = {x["id"]: LectureBox(x["id"], x["title"], tuple(x["position"]), tuple(x["size"]))
                 for x in value["lecture_boxes"].values()}
        cards = {x["id"]: Card(x["id"], x["note_kind"], x["title"], x["summary"],
                                tuple(x["position"]), tuple(x["size"]), x["lecture_box_id"])
                 for x in value["cards"].values()}
        edges = {x["id"]: Edge(x["id"], x["kind"], x["source_card_id"], x["target_card_id"],
                                x["label"], [RelativeControlPoint(**cp) for cp in x["control_points"]])
                 for x in value["edges"].values()}
        result = cls(value["course_id"], boxes, cards, edges, set(value["hidden_card_types"]))
        for edge in result.edges.values(): result.assert_edge_is_allowed(edge)
        return result


def fixture() -> CourseMap:
    boxes = {
        "lecture-vectors": LectureBox("lecture-vectors", "Векторы", (40, 40), (380, 280)),
        "lecture-matrices": LectureBox("lecture-matrices", "Матрицы", (540, 40), (420, 280)),
    }
    cards = {
        "vector": Card("vector", "concept", "Вектор", "Элемент векторного пространства", (100, 150), lecture_box_id="lecture-vectors"),
        "matrix": Card("matrix", "concept", "Матрица", "Прямоугольная таблица чисел", (620, 150), lecture_box_id="lecture-matrices"),
        "diagonal": Card("diagonal", "concept", "Диагональная матрица", "Матрица с нулями вне диагонали", (620, 245), lecture_box_id="lecture-matrices"),
        "symmetric": Card("symmetric", "concept", "Симметричная матрица", "Равна транспонированной", (790, 245), lecture_box_id="lecture-matrices"),
        "cosine": Card("cosine", "externalConcept", "Косинус", "Внешнее понятие", (1010, 130)),
        "example": Card("example", "example", "Пример скалярного произведения", "Пример", (1000, 230)),
        "task": Card("task", "task", "Задача на диагональность", "Задача", (1000, 330)),
    }
    result = CourseMap("linear-algebra", boxes, cards, {})
    result.add_edge(Edge("context-vector-matrix", "contextual", "vector", "matrix", "матрица — группа векторов"))
    result.set_control_point_from_world("context-vector-matrix", 0, (400, 80))
    result.set_control_point_from_world("context-vector-matrix", 1, (540, 290))
    result.add_edge(Edge("h-matrix-diagonal", "hierarchical", "matrix", "diagonal"))
    result.add_edge(Edge("h-diagonal-symmetric", "hierarchical", "diagonal", "symmetric"))
    result.add_edge(Edge("h-symmetric-matrix", "hierarchical", "symmetric", "matrix"))
    result.add_edge(Edge("mention", "mention", "cosine", "vector"))
    result.add_edge(Edge("example-vector", "exampleAttachment", "example", "vector"))
    result.add_edge(Edge("example-matrix", "exampleAttachment", "example", "matrix"))
    result.add_edge(Edge("task-matrix", "taskAttachment", "task", "matrix"))
    result.add_edge(Edge("task-diagonal", "taskAttachment", "task", "diagonal"))
    return result


class MapSpikeTests(unittest.TestCase):
    def test_fixture_is_two_lectures_cross_lecture_labelled_context_and_cycle(self) -> None:
        course = fixture()
        self.assertEqual(2, len(course.lecture_boxes))
        context = course.edges["context-vector-matrix"]
        self.assertEqual("матрица — группа векторов", context.label)
        self.assertNotEqual(course.cards[context.source_card_id].lecture_box_id,
                            course.cards[context.target_card_id].lecture_box_id)
        self.assertEqual(["matrix", "diagonal", "symmetric", "matrix"],
                         [course.edges[x].source_card_id for x in ["h-matrix-diagonal", "h-diagonal-symmetric", "h-symmetric-matrix"]] + ["matrix"])

    def test_control_points_survive_endpoint_and_container_move_and_reload(self) -> None:
        course = fixture()
        before = course.path("context-vector-matrix")
        course.move_card("vector", (30, -20))
        after_endpoint_move = course.path("context-vector-matrix")
        self.assertNotEqual(before, after_endpoint_move)
        self.assertEqual(4, len(after_endpoint_move))
        course.move_lecture_box("lecture-matrices", (70, 30))
        reloaded = CourseMap.from_json(course.to_json())
        self.assertEqual(course.path("context-vector-matrix"), reloaded.path("context-vector-matrix"))
        self.assertEqual("матрица — группа векторов", reloaded.edges["context-vector-matrix"].label)

    def test_type_filter_is_non_destructive_and_hides_incident_edges(self) -> None:
        course = fixture()
        course.hidden_card_types.add("externalConcept")
        cards, edges = course.visible()
        self.assertNotIn("cosine", cards)
        self.assertNotIn("mention", edges)
        self.assertIn("cosine", course.cards)
        self.assertIn("mention", course.edges)

    def test_incompatible_hierarchy_is_rejected_but_cycle_is_not(self) -> None:
        course = fixture()
        with self.assertRaises(ValueError):
            course.add_edge(Edge("bad", "hierarchical", "cosine", "vector"))
        self.assertIn("h-symmetric-matrix", course.edges)


if __name__ == "__main__":
    unittest.main(verbosity=2)
