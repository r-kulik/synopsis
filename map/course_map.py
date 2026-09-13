from __future__ import annotations
from dataclasses import dataclass
from synopsis_domain import CourseSnapshot, Point
from geometry import edge_path
from map_settings import MapSettings


@dataclass(frozen=True)
class CourseRoot:
    course_id: str
    title: str


@dataclass(frozen=True)
class MapLectureBox:
    id: str
    title: str
    position: Point
    size: Point


@dataclass(frozen=True)
class MapCard:
    id: str
    note_id: str
    kind: str
    title: str
    summary: str
    position: Point
    size: Point
    lecture_box_id: str | None
    appearance: dict | None


@dataclass(frozen=True)
class MapEdge:
    id: str
    kind: str
    source_card_id: str
    target_card_id: str
    label: str | None
    path: list[Point]


@dataclass(frozen=True)
class CourseMap:
    root: CourseRoot
    lecture_boxes: list[MapLectureBox]
    cards: list[MapCard]
    edges: list[MapEdge]
    settings: MapSettings

    @classmethod
    def from_snapshot(cls, snapshot: CourseSnapshot) -> "CourseMap":
        settings = MapSettings.from_course_settings(snapshot.course.settings)
        cards = []
        visible_ids = set()
        for card in snapshot.cards.values():
            note = snapshot.notes.get(card.note_id)
            if note is None or note.kind.value == "lecture" or note.kind.value in settings.hidden_note_kinds:
                continue
            visible_ids.add(card.id)
            cards.append(MapCard(str(card.id), str(card.note_id), note.kind.value, note.title, note.summary, card.position, card.size, str(card.lecture_box_id) if card.lecture_box_id else None, card.appearance))
        boxes = [MapLectureBox(str(box.id), snapshot.notes[box.note_id].title, box.position, box.size)
                 for box in snapshot.lecture_boxes.values() if box.note_id in snapshot.notes]
        edges = []
        for edge in snapshot.edges.values():
            if edge.source_card_id not in visible_ids or edge.target_card_id not in visible_ids:
                continue
            source, target = snapshot.cards[edge.source_card_id], snapshot.cards[edge.target_card_id]
            source_center = Point(source.position.x + source.size.x / 2, source.position.y + source.size.y / 2)
            target_center = Point(target.position.x + target.size.x / 2, target.position.y + target.size.y / 2)
            edges.append(MapEdge(str(edge.id), edge.kind.value, str(edge.source_card_id), str(edge.target_card_id), edge.label, edge_path(source_center, target_center, edge.geometry.control_points)))
        return cls(CourseRoot(str(snapshot.course.id), snapshot.course.title), boxes, cards, edges, settings)
