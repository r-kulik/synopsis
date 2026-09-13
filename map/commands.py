from __future__ import annotations
from copy import deepcopy
from uuid import uuid4
from synopsis_domain import Card, CardId, CourseService, CourseSnapshot, Edge, EdgeGeometry, EdgeId, EdgeKind, LectureBoxId, NoteId, Point
from geometry import world_to_control
from map_settings import MapSettings


class MapCommands:
    """Atomic map-only operations. Host persists ``state`` after a successful command.

    This is deliberately a command boundary over S01's snapshot: it never reads or
    derives graph relations from Note.markdown.
    """
    def __init__(self, snapshot: CourseSnapshot): self.state = snapshot

    def _atomic(self, action):
        before = deepcopy(self.state)
        try:
            value = action(); self.state.course.saved_revision += 1; return value
        except Exception:
            self.state = before
            raise

    def move_card(self, card_id: str, delta: Point) -> Card:
        def action():
            card = self.state.cards[CardId(card_id)]
            card.position = Point(card.position.x + delta.x, card.position.y + delta.y)
            return card
        return self._atomic(action)

    def move_lecture_box(self, box_id: str, delta: Point) -> None:
        def action():
            box = self.state.lecture_boxes[LectureBoxId(box_id)]
            box.position = Point(box.position.x + delta.x, box.position.y + delta.y)
            for card in self.state.cards.values():
                if card.lecture_box_id == box.id:
                    card.position = Point(card.position.x + delta.x, card.position.y + delta.y)
        self._atomic(action)

    def create_edge(self, *, edge_id: str | None, kind: EdgeKind, source_card_id: str, target_card_id: str, label: str | None = None) -> Edge:
        edge = Edge(EdgeId(edge_id or str(uuid4())), self.state.course.id, kind, CardId(source_card_id), CardId(target_card_id), label)
        # Reuse the canonical compatibility/multiple-parent/cycle rules.
        service = CourseService(self.state)
        return service.create_edge(edge)

    def set_edge_label(self, edge_id: str, label: str | None) -> Edge:
        def action():
            edge = self.state.edges[EdgeId(edge_id)]; edge.label = label; return edge
        return self._atomic(action)

    def set_control_point(self, edge_id: str, index: int, world: Point) -> Edge:
        def action():
            edge = self.state.edges[EdgeId(edge_id)]
            source, target = self.state.cards[edge.source_card_id], self.state.cards[edge.target_card_id]
            s = Point(source.position.x + source.size.x / 2, source.position.y + source.size.y / 2)
            t = Point(target.position.x + target.size.x / 2, target.position.y + target.size.y / 2)
            relative = world_to_control(s, t, world)
            if not 0 <= index <= len(edge.geometry.control_points): raise ValueError("control point index is invalid")
            if index == len(edge.geometry.control_points): edge.geometry.control_points.append(relative)
            else: edge.geometry.control_points[index] = relative
            return edge
        return self._atomic(action)

    def remove_control_point(self, edge_id: str, index: int) -> None:
        self._atomic(lambda: self.state.edges[EdgeId(edge_id)].geometry.control_points.pop(index))

    def set_settings(self, settings: MapSettings) -> None:
        self._atomic(lambda: settings.write_to_course_settings(self.state.course.settings))

    def remove_card(self, card_id: str) -> None:
        CourseService(self.state).remove_card(CardId(card_id))

    def recreate_card(self, note_id: str, position: Point, *, card_id: str | None = None) -> Card:
        card = Card(CardId(card_id or str(uuid4())), self.state.course.id, NoteId(note_id), position)
        return CourseService(self.state).create_card(card)

    def remove_lecture_box(self, box_id: str) -> None:
        CourseService(self.state).remove_lecture_box(LectureBoxId(box_id))
