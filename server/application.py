from __future__ import annotations
from copy import deepcopy
from uuid import uuid4
from synopsis_domain import Card, CardId, Course, CourseId, CourseService, CourseSnapshot, LectureBox, LectureBoxId, Note, NoteId, NoteKind, Point
from storage import FileCourseStorage

class SynopsisApplication:
    """Persistence-aware command boundary used by HTTP and future UI modules."""
    def __init__(self, storage: FileCourseStorage): self.storage = storage
    def list_courses(self): return self.storage.list_courses()
    def create_course(self, title: str):
        if not title.strip(): raise ValueError("course title is required")
        snapshot = CourseSnapshot(Course(CourseId(str(uuid4())), title.strip())); self.storage.save(snapshot); return snapshot.course
    def snapshot(self, course_id: str): return self.storage.load(course_id)
    def _commit(self, course_id, command):
        snapshot = self.storage.load(course_id); before = deepcopy(snapshot); service = CourseService(snapshot)
        try:
            value = command(service); self.storage.save(service.state); return value
        except Exception:
            service.state = before; raise
    def create_note(self, course_id: str, *, kind: str, title: str, summary="", markdown="", with_card=False):
        note = Note(NoteId(str(uuid4())), CourseId(course_id), NoteKind(kind), title, summary, markdown)
        def command(service):
            if note.id in service.state.notes: raise ValueError("duplicate note")
            service.state.notes[note.id] = note; service.state.course.saved_revision += 1
            if with_card: service.create_card(Card(CardId(str(uuid4())), CourseId(course_id), note.id, Point(40, 40)))
            return note
        return self._commit(course_id, command)
    def create_card(self, course_id: str, note_id: str):
        return self._commit(course_id, lambda s: s.create_card(Card(CardId(str(uuid4())), CourseId(course_id), NoteId(note_id), Point(40, 40))))
    def create_lecture(self, course_id: str, title: str):
        note = Note(NoteId(str(uuid4())), CourseId(course_id), NoteKind.LECTURE, title, "", "")
        box = LectureBox(LectureBoxId(str(uuid4())), CourseId(course_id), note.id, Point(20, 20), Point(400, 260))
        def command(service):
            service.state.notes[note.id] = note; service.state.lecture_boxes[box.id] = box; service.state.course.saved_revision += 1
            return note, box
        return self._commit(course_id, command)
    def import_asset(self, course_id: str, original_name: str, media_type: str, content: bytes):
        asset_id = str(uuid4())
        asset = self.storage.put_asset(course_id, asset_id, original_name, media_type, content)
        def command(service):
            service.state.assets[asset.id] = asset; service.state.course.saved_revision += 1; return asset
        try: return self._commit(course_id, command)
        except Exception:
            # Bytes without metadata are inaccessible; a retry can use a new ID.
            raise
    def save_markdown(self, course_id: str, note_id: str, markdown: str, revision: int):
        return self._commit(course_id, lambda s: s.save_markdown(NoteId(note_id), markdown, revision))
