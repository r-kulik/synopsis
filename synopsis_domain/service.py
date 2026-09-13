from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum
from typing import Callable

from .model import *
from .url import make_internal_url
from .url import InternalAddress, parse_internal_url


class ErrorCode(StrEnum):
    NOT_FOUND = "notFound"; COURSE_MISMATCH = "courseMismatch"; REVISION_CONFLICT = "revisionConflict"
    INVALID_EDGE = "invalidEdge"; VALIDATION = "validation"


class DomainError(ValueError):
    def __init__(self, code: ErrorCode, message: str): self.code, self.message = code, message; super().__init__(message)


EDGE_ENDPOINTS = {
    EdgeKind.CONTEXTUAL: (NoteKind.CONCEPT, NoteKind.CONCEPT),
    EdgeKind.HIERARCHICAL: (NoteKind.CONCEPT, NoteKind.CONCEPT),
    EdgeKind.MENTION: (NoteKind.EXTERNAL_CONCEPT, NoteKind.CONCEPT),
    EdgeKind.EXAMPLE_ATTACHMENT: (NoteKind.EXAMPLE, NoteKind.CONCEPT),
    EdgeKind.TASK_ATTACHMENT: (NoteKind.TASK, NoteKind.CONCEPT),
}


class CourseService:
    """Command boundary. Each mutating command is atomic: it rolls back its snapshot on error."""
    def __init__(self, snapshot: CourseSnapshot): self.state = snapshot

    def _atomic(self, command: Callable[[], object]):
        before = deepcopy(self.state)
        try:
            value = command(); self.state.course.saved_revision += 1; return value
        except Exception:
            self.state = before; raise

    def _note(self, note_id: NoteId) -> Note:
        try: return self.state.notes[note_id]
        except KeyError: raise DomainError(ErrorCode.NOT_FOUND, "note does not exist")

    def save_markdown(self, note_id: NoteId, markdown: str, expected_revision: int) -> Note:
        def command():
            note = self._note(note_id)
            if note.revision != expected_revision: raise DomainError(ErrorCode.REVISION_CONFLICT, "note revision is stale")
            note.markdown = markdown; note.revision += 1; return note
        return self._atomic(command)

    def apply_source_patch(self, note_id: NoteId, expected_revision: int, start: int, end: int, replacement: str) -> Note:
        """The renderer supplies already validated raw source offsets; no document reserialization occurs."""
        def command():
            note = self._note(note_id)
            if note.revision != expected_revision: raise DomainError(ErrorCode.REVISION_CONFLICT, "note revision is stale")
            if not (0 <= start <= end <= len(note.markdown)): raise DomainError(ErrorCode.VALIDATION, "invalid source patch range")
            note.markdown = note.markdown[:start] + replacement + note.markdown[end:]
            note.revision += 1; return note
        return self._atomic(command)

    def resolve_internal_url(self, raw: str) -> InternalAddress | None:
        """A malformed or dangling textual URL is safely unresolved, never a save failure."""
        address = parse_internal_url(raw)
        if address is None: return None
        exists = {
            "note": address.id in self.state.notes,
            "fact": address.id in self.state.facts,
            "source": address.id in self.state.sources,
            "asset": address.id in self.state.assets,
        }[address.resource]
        if not exists: return None
        if address.resource == "fact" and self.state.facts[FactId(address.id)].owner_note_id not in self.state.notes: return None
        if address.resource == "source" and address.page and self.state.sources[SourceId(address.id)].page_count is not None and address.page > self.state.sources[SourceId(address.id)].page_count: return None
        return address

    def create_card(self, card: Card) -> Card:
        def command():
            note = self._note(card.note_id)
            if card.course_id != self.state.course.id or note.course_id != card.course_id: raise DomainError(ErrorCode.COURSE_MISMATCH, "card and note must share course")
            if any(x.note_id == card.note_id for x in self.state.cards.values()): raise DomainError(ErrorCode.VALIDATION, "a note has at most one card")
            self.state.cards[card.id] = card; return card
        return self._atomic(command)

    def create_edge(self, edge: Edge) -> Edge:
        def command():
            try: source, target = self.state.cards[edge.source_card_id], self.state.cards[edge.target_card_id]
            except KeyError: raise DomainError(ErrorCode.NOT_FOUND, "edge endpoint card does not exist")
            if edge.course_id != self.state.course.id or source.course_id != edge.course_id or target.course_id != edge.course_id: raise DomainError(ErrorCode.COURSE_MISMATCH, "edge endpoints must share course")
            kinds = (self._note(source.note_id).kind, self._note(target.note_id).kind)
            if kinds != EDGE_ENDPOINTS[edge.kind]: raise DomainError(ErrorCode.INVALID_EDGE, "incompatible edge endpoints")
            if edge.source_card_id == edge.target_card_id: raise DomainError(ErrorCode.INVALID_EDGE, "self-loop is not supported in v1")
            self.state.edges[edge.id] = edge; return edge
        return self._atomic(command)

    def remove_card(self, card_id: CardId) -> None:
        def command():
            if card_id not in self.state.cards: raise DomainError(ErrorCode.NOT_FOUND, "card does not exist")
            del self.state.cards[card_id]
            self.state.edges = {k:v for k,v in self.state.edges.items() if v.source_card_id != card_id and v.target_card_id != card_id}
        self._atomic(command)

    def remove_lecture_box(self, box_id: LectureBoxId) -> None:
        def command():
            if box_id not in self.state.lecture_boxes: raise DomainError(ErrorCode.NOT_FOUND, "lecture box does not exist")
            del self.state.lecture_boxes[box_id]
            for card in self.state.cards.values():
                if card.lecture_box_id == box_id: card.lecture_box_id = None  # position is already world-space
        self._atomic(command)

    def delete_note(self, note_id: NoteId) -> None:
        def command():
            self._note(note_id)
            cards = {id for id, x in self.state.cards.items() if x.note_id == note_id}
            self.state.cards = {id:x for id,x in self.state.cards.items() if id not in cards}
            self.state.edges = {id:x for id,x in self.state.edges.items() if x.source_card_id not in cards and x.target_card_id not in cards}
            removed_boxes = {id for id,x in self.state.lecture_boxes.items() if x.note_id == note_id}
            for card in self.state.cards.values():
                if card.lecture_box_id in removed_boxes:
                    card.lecture_box_id = None
            self.state.lecture_boxes = {id:x for id,x in self.state.lecture_boxes.items() if x.note_id != note_id}
            self.state.lecture_source_attachments = [a for a in self.state.lecture_source_attachments if a.lecture_note_id != note_id]
            self.state.facts = {id:x for id,x in self.state.facts.items() if x.owner_note_id != note_id}
            for note in self.state.notes.values():
                if note.defined_in_lecture_note_id == note_id: note.defined_in_lecture_note_id = None
            del self.state.notes[note_id]  # Markdown elsewhere is deliberately untouched.
        self._atomic(command)

    def create_note_from_selection(self, *, source_note_id: NoteId, expected_revision: int, raw_start: int, raw_end: int, note: Note, card: Card) -> Note:
        def command():
            source = self._note(source_note_id)
            if source.revision != expected_revision: raise DomainError(ErrorCode.REVISION_CONFLICT, "selection revision is stale")
            if not (0 <= raw_start < raw_end <= len(source.markdown)): raise DomainError(ErrorCode.VALIDATION, "invalid source range")
            if note.id in self.state.notes or card.id in self.state.cards: raise DomainError(ErrorCode.VALIDATION, "duplicate id")
            if note.course_id != source.course_id or card.course_id != source.course_id or card.note_id != note.id: raise DomainError(ErrorCode.COURSE_MISMATCH, "selection result must be in source course")
            selected = source.markdown[raw_start:raw_end]
            source.markdown = source.markdown[:raw_start] + f"[{selected}]({make_internal_url('note', note.id)})" + source.markdown[raw_end:]
            source.revision += 1; self.state.notes[note.id] = note; self.state.cards[card.id] = card
            return note
        return self._atomic(command)

    def create_fact(self, fact: Fact) -> Fact:
        def command():
            owner = self._note(fact.owner_note_id)
            if fact.course_id != owner.course_id: raise DomainError(ErrorCode.COURSE_MISMATCH, "fact owner must share course")
            self.state.facts[fact.id] = fact; return fact
        return self._atomic(command)
