"""S05 reading-mode selection adapters.

This module consumes, rather than widens, S03's deliberately small source-map
contract.  It has no DOM dependency: a browser adapter must convert its Range
to offsets in one ``SourceSpan`` before calling it.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from render import RenderedMarkdown, SourceSpan
from synopsis_domain import Card, CourseService, DomainError, ErrorCode, Note, NoteId, make_internal_url


class SelectionError(ValueError):
    """A refused selection; callers must display this and make no write."""


@dataclass(frozen=True)
class SelectionRange:
    note_id: NoteId
    revision: int
    span: SourceSpan
    rendered_start: int
    rendered_end: int
    selected_text: str

    def raw_range(self) -> tuple[int, int]:
        if not self.span.selectable or not (0 <= self.rendered_start < self.rendered_end <= len(self.span.rendered_text)):
            raise SelectionError("Selection is outside a supported plain-text source span")
        actual = self.span.rendered_text[self.rendered_start:self.rendered_end]
        if actual != self.selected_text:
            raise SelectionError("Selection text no longer matches its rendered source span")
        return self.span.raw_start + self.rendered_start, self.span.raw_start + self.rendered_end


def selection_from_rendered(*, note_id: NoteId, revision: int, rendered: RenderedMarkdown,
                            span_index: int, rendered_start: int, rendered_end: int,
                            selected_text: str) -> SelectionRange:
    """Build a range only from exactly one S03 span (never infer cross-span text)."""
    try:
        span = rendered.spans[span_index]
    except IndexError as exc:
        raise SelectionError("Selection has no supported source span") from exc
    request = SelectionRange(note_id, revision, span, rendered_start, rendered_end, selected_text)
    request.raw_range()
    return request


def _checked_range(service: CourseService, request: SelectionRange) -> tuple[int, int]:
    start, end = request.raw_range()
    try:
        note = service.state.notes[request.note_id]
    except KeyError as exc:
        raise DomainError(ErrorCode.NOT_FOUND, "source note does not exist") from exc
    if note.revision != request.revision:
        raise DomainError(ErrorCode.REVISION_CONFLICT, "selection revision is stale")
    if note.markdown[start:end] != request.selected_text:
        raise SelectionError("Rendered selection does not match current Markdown")
    return start, end


def find_notes_in_course(service: CourseService, query: str = "") -> list[Note]:
    """Lookup includes cardless Notes and cannot escape the current course."""
    needle = query.casefold()
    return sorted((note for note in service.state.notes.values()
                   if note.course_id == service.state.course.id
                   and (not needle or needle in note.title.casefold() or needle in note.summary.casefold())),
                  key=lambda note: (note.title.casefold(), str(note.id)))


def link_selection_to_note(service: CourseService, request: SelectionRange, target_note_id: NoteId):
    start, end = _checked_range(service, request)
    target = service.state.notes.get(target_note_id)
    if target is None:
        raise DomainError(ErrorCode.NOT_FOUND, "link target note does not exist")
    if target.course_id != service.state.course.id:
        raise DomainError(ErrorCode.COURSE_MISMATCH, "link target is outside this course")
    return service.apply_source_patch(request.note_id, request.revision, start, end,
                                      f"[{request.selected_text}]({make_internal_url('note', target_note_id)})")


@dataclass(frozen=True)
class FreeCardPlacement:
    """A visible position supplied by the map host; S05 never auto-creates edges."""
    x: float
    y: float

    def validate(self) -> None:
        if not isfinite(self.x) or not isfinite(self.y):
            raise SelectionError("A finite free card position is required")


def create_note_from_selection(service: CourseService, request: SelectionRange, note: Note, card: Card,
                               placement: FreeCardPlacement) -> Note:
    """Delegate the all-or-nothing Note/Card/patch command fixed by ADR-002."""
    placement.validate()
    start, end = _checked_range(service, request)
    if (card.position.x, card.position.y) != (placement.x, placement.y):
        raise SelectionError("Card must use the explicitly requested free position")
    before_edges = dict(service.state.edges)
    created = service.create_note_from_selection(source_note_id=request.note_id, expected_revision=request.revision,
                                                  raw_start=start, raw_end=end, note=note, card=card)
    if service.state.edges != before_edges:  # defensive: text selection never implies an edge
        raise RuntimeError("CreateNoteFromSelection unexpectedly created an edge")
    return created
