"""Fact marker lifecycle for S05; facts remain separate from map entities."""
from __future__ import annotations

import re
from dataclasses import dataclass

from selection import SelectionRange, _checked_range
from synopsis_domain import CourseService, DomainError, ErrorCode, Fact, FactId, NoteId, make_internal_url, parse_internal_url

_URL = re.compile(r"\]\((synopsis://[^ )]+)\)")


def create_fact_from_selection(service: CourseService, request: SelectionRange, fact: Fact) -> Fact:
    """Create Fact and its owner marker in one CourseService atomic boundary."""
    start, end = _checked_range(service, request)
    def command():
        source = service._note(request.note_id)
        if fact.id in service.state.facts:
            raise DomainError(ErrorCode.VALIDATION, "duplicate fact id")
        if fact.owner_note_id != source.id or fact.course_id != source.course_id:
            raise DomainError(ErrorCode.COURSE_MISMATCH, "fact must belong to the selected note and course")
        source.markdown = source.markdown[:start] + f"[{request.selected_text}]({make_internal_url('fact', fact.id)})" + source.markdown[end:]
        source.revision += 1
        service.state.facts[fact.id] = fact
        return fact
    return service._atomic(command)


def edit_fact(service: CourseService, fact_id: FactId, owner_note_id: NoteId, markdown: str) -> Fact:
    def command():
        try: fact = service.state.facts[fact_id]
        except KeyError: raise DomainError(ErrorCode.NOT_FOUND, "fact does not exist")
        if fact.owner_note_id != owner_note_id:
            raise DomainError(ErrorCode.COURSE_MISMATCH, "fact belongs to a different note")
        fact.markdown = markdown
        return fact
    return service._atomic(command)


def attached_fact_ids(service: CourseService, owner_note_id: NoteId) -> set[FactId]:
    """Recomputable marker index; a foreign fact URL never attaches to this Note."""
    note = service._note(owner_note_id)
    attached: set[FactId] = set()
    for raw in _URL.findall(note.markdown):
        address = parse_internal_url(raw)
        if address and address.resource == "fact":
            fact = service.state.facts.get(FactId(address.id))
            if fact is not None and fact.owner_note_id == owner_note_id:
                attached.add(fact.id)
    return attached


def orphan_facts(service: CourseService, owner_note_id: NoteId) -> list[Fact]:
    attached = attached_fact_ids(service, owner_note_id)
    return [fact for fact in service.state.facts.values()
            if fact.owner_note_id == owner_note_id and fact.id not in attached]
