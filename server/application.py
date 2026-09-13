"""Local application service: serialized, durable commands over course snapshots."""
from __future__ import annotations
from functools import wraps
from math import isfinite
from threading import RLock
from uuid import uuid4
from synopsis_domain import (
    Card, CardId, Course, CourseId, CourseService, CourseSnapshot, EdgeId, EdgeKind,
    Fact, FactId, LectureBox, LectureBoxId, Note, NoteId, NoteKind, Point, Source, SourceId,
    make_internal_url,
)
from storage import FileCourseStorage
from map import MapCommands
from map_settings import MapSettings
from selection import selection_from_rendered
from facts import edit_fact
from source_links import attach_pdf_to_lecture, external_open_intent, make_source_url
from render import render_markdown
from transfer import export_course, import_course
from .selection_patch import checked_browser_range


def serialized(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapped


def title_text(value):
    if not isinstance(value, str) or not value.strip(): raise ValueError("Введите название")
    if len(value) > 500: raise ValueError("Название не должно превышать 500 символов")
    return value.strip()


def point(value):
    result = Point(float(value["x"]), float(value["y"]))
    if not isfinite(result.x) or not isfinite(result.y) or max(abs(result.x), abs(result.y)) > 1e7:
        raise ValueError("Некорректные координаты")
    return result


class SynopsisApplication:
    def __init__(self, storage: FileCourseStorage):
        self.storage = storage
        self._lock = RLock()

    @serialized
    def list_courses(self): return self.storage.list_courses()

    @serialized
    def create_course(self, title):
        snapshot = CourseSnapshot(Course(CourseId(str(uuid4())), title_text(title)))
        self.storage.save(snapshot)
        return snapshot.course

    @serialized
    def snapshot(self, course_id): return self.storage.load(course_id)

    @serialized
    def _commit(self, course_id, command):
        service = CourseService(self.storage.load(course_id))
        value = command(service)
        self.storage.save(service.state)
        return value

    def rename_course(self, course_id, title):
        def command(service):
            service.state.course.title = title_text(title)
            service.state.course.saved_revision += 1
            return service.state.course
        return self._commit(course_id, command)

    @staticmethod
    def _free_position(snapshot, preferred=None, size=Point(220,100), ignore_box=None):
        start = point(preferred) if preferred else Point(70,140)
        obstacles = [(c.position,c.size) for c in snapshot.cards.values()]
        obstacles += [(b.position,b.size) for b in snapshot.lecture_boxes.values() if b.id != ignore_box]
        for row in range(10000):
            for col in range(2):
                p = Point(start.x+col*(size.x+35),start.y+row*(size.y+35))
                if all(p.x+size.x+16<=q.x or p.x>=q.x+s.x+16 or p.y+size.y+16<=q.y or p.y>=q.y+s.y+16 for q,s in obstacles): return p
        raise ValueError("Не удалось найти свободное место на карте")

    @staticmethod
    def _lecture(snapshot, lecture_id):
        lecture = snapshot.notes.get(NoteId(lecture_id)) if lecture_id else None
        if lecture_id and (lecture is None or lecture.kind != NoteKind.LECTURE): raise ValueError("Лекция не найдена в текущем курсе")
        box = next((b for b in snapshot.lecture_boxes.values() if b.note_id == lecture_id),None)
        return lecture,box

    def create_note(self, course_id, *, kind, title, summary="", markdown="", with_card=False, lecture_note_id=None, position=None):
        if not isinstance(summary,str) or not isinstance(markdown,str): raise ValueError("Описание и Markdown должны быть строками")
        if kind == "lecture": return self.create_lecture(course_id,title,summary=summary,markdown=markdown,position=position)[0]
        note = Note(NoteId(str(uuid4())),CourseId(course_id),NoteKind(kind),title_text(title),summary,markdown)
        def command(service):
            lecture,box = self._lecture(service.state,lecture_note_id)
            if lecture and note.kind == NoteKind.CONCEPT: note.defined_in_lecture_note_id = lecture.id
            service.state.notes[note.id] = note
            service.state.course.saved_revision += 1
            if with_card:
                preferred = position or ({"x":box.position.x+25,"y":box.position.y+60} if box else None)
                p = self._free_position(service.state,preferred,ignore_box=box.id if box else None)
                card = Card(CardId(str(uuid4())),CourseId(course_id),note.id,p,Point(220,100),box.id if box else None)
                service.create_card(card)
                if box: self._fit_box(box,card)
            return note
        return self._commit(course_id,command)

    @staticmethod
    def _fit_box(box,card):
        box.size = Point(max(box.size.x,card.position.x+card.size.x+25-box.position.x),max(box.size.y,card.position.y+card.size.y+25-box.position.y))

    def create_card(self,course_id,note_id):
        return self.command_map(course_id,"show-card",{"note_id":note_id})

    def create_lecture(self,course_id,title,*,summary="",markdown="",position=None):
        if not isinstance(summary,str) or not isinstance(markdown,str): raise ValueError("Описание и Markdown должны быть строками")
        def command(service):
            note = Note(NoteId(str(uuid4())),CourseId(course_id),NoteKind.LECTURE,title_text(title),summary,markdown)
            p = self._free_position(service.state,position,size=Point(540,360))
            box = LectureBox(LectureBoxId(str(uuid4())),CourseId(course_id),note.id,p,Point(540,360))
            service.state.notes[note.id] = note
            service.state.lecture_boxes[box.id] = box
            service.state.course.saved_revision += 1
            return note,box
        return self._commit(course_id,command)

    def edit_note_meta(self,course_id,note_id,data):
        def command(service):
            note = service._note(NoteId(note_id))
            if "title" in data: note.title = title_text(data["title"])
            if "summary" in data: note.summary = str(data["summary"])
            if "defined_in_lecture_note_id" in data:
                lecture,box = self._lecture(service.state,data["defined_in_lecture_note_id"])
                if note.kind == NoteKind.CONCEPT: note.defined_in_lecture_note_id = lecture.id if lecture else None
                for card in service.state.cards.values():
                    if card.note_id == note.id:
                        card.lecture_box_id = box.id if box else None
                        if box:
                            card.position = self._free_position(service.state,{"x":box.position.x+25,"y":box.position.y+60},card.size,box.id)
                            self._fit_box(box,card)
            service.state.course.saved_revision += 1
            return note
        return self._commit(course_id,command)

    @serialized
    def import_asset(self,course_id,original_name,media_type,content):
        if media_type not in {"application/pdf","image/png","image/jpeg","image/gif","image/webp","image/avif"}: raise ValueError("Поддерживаются PDF, PNG, JPEG, GIF, WebP и AVIF")
        if not content: raise ValueError("Файл пуст")
        if len(content)>32*1024*1024: raise ValueError("Размер одного вложения — не больше 32 MiB")
        asset = self.storage.put_asset(course_id,str(uuid4()),original_name,media_type,content)
        def command(service):
            service.state.assets[asset.id] = asset
            service.state.course.saved_revision += 1
            return asset
        return self._commit(course_id,command)

    @serialized
    def import_source(self,course_id,filename,content,lecture_note_id=None):
        if len(content)>32*1024*1024: raise ValueError("Размер одного PDF — не больше 32 MiB")
        if not content.lstrip().startswith(b"%PDF-"): raise ValueError("Файл не является PDF")
        snapshot = self.storage.load(course_id)
        if lecture_note_id: self._lecture(snapshot,lecture_note_id)
        asset = self.storage.put_asset(course_id,str(uuid4()),filename,"application/pdf",content)
        source = Source(SourceId(str(uuid4())),snapshot.course.id,filename,asset.id)
        def command(service):
            service.state.assets[asset.id] = asset
            service.state.sources[source.id] = source
            if lecture_note_id: attach_pdf_to_lecture(service,NoteId(lecture_note_id),source.id)
            service.state.course.saved_revision += 1
            return source
        return self._commit(course_id,command)

    def source_command(self,course_id,source_id,name,data):
        def command(service):
            source = service.state.sources.get(SourceId(source_id))
            if not source: raise ValueError("Источник не найден")
            if name == "rename": source.title = title_text(data["title"])
            elif name == "attach": attach_pdf_to_lecture(service,NoteId(data["lecture_note_id"]),source.id,data.get("page"))
            else: raise ValueError("Неизвестное действие источника")
            service.state.course.saved_revision += 1
            return source
        return self._commit(course_id,command)

    def source_open(self,course_id,source_id,page=None):
        service = CourseService(self.snapshot(course_id))
        intent = external_open_intent(service,SourceId(source_id),page)
        self.storage.get_asset(course_id,service.state.sources[SourceId(source_id)].asset_id)
        return intent

    def save_markdown(self,course_id,note_id,markdown,revision):
        if not isinstance(markdown,str): raise ValueError("Markdown должен быть строкой")
        return self._commit(course_id,lambda s:s.save_markdown(NoteId(note_id),markdown,revision))

    @serialized
    def command_map(self,course_id,name,data):
        snapshot = self.storage.load(course_id)
        commands = MapCommands(snapshot)
        if name == "move-card": value = commands.move_card(data["card_id"],point(data["delta"]))
        elif name == "move-box": value = commands.move_lecture_box(data["box_id"],point(data["delta"]))
        elif name == "remove-card": value = commands.remove_card(data["card_id"])
        elif name == "show-card":
            note = snapshot.notes[NoteId(data["note_id"])]
            if note.kind == NoteKind.LECTURE:
                value = next((b for b in snapshot.lecture_boxes.values() if b.note_id == note.id),None)
                if value is None:
                    value = LectureBox(LectureBoxId(str(uuid4())),snapshot.course.id,note.id,self._free_position(snapshot,size=Point(540,360)),Point(540,360))
                    snapshot.lecture_boxes[value.id] = value
                    snapshot.course.saved_revision += 1
            else:
                value = next((c for c in snapshot.cards.values() if c.note_id == note.id),None)
                if value is None:
                    _,box=self._lecture(snapshot,note.defined_in_lecture_note_id)
                    preferred={"x":box.position.x+25,"y":box.position.y+60} if box else data.get("position")
                    value = commands.recreate_card(note.id,self._free_position(snapshot,preferred,ignore_box=box.id if box else None))
                    value.size = Point(220,100)
                    value.lecture_box_id=box.id if box else None
                    if box:self._fit_box(box,value)
        elif name == "remove-box": value = commands.remove_lecture_box(data["box_id"])
        elif name == "edge": value = commands.create_edge(edge_id=None,kind=EdgeKind(data["kind"]),source_card_id=data["source_card_id"],target_card_id=data["target_card_id"],label=data.get("label"))
        elif name == "edge-label": value = commands.set_edge_label(data["edge_id"],data.get("label"))
        elif name == "control": value = commands.set_control_point(data["edge_id"],int(data["index"]),point(data["position"]))
        elif name == "remove-control": value = commands.remove_control_point(data["edge_id"],int(data["index"]))
        elif name == "remove-edge": value = snapshot.edges.pop(EdgeId(data["edge_id"]));snapshot.course.saved_revision+=1
        elif name == "resize-box":
            box = snapshot.lecture_boxes[LectureBoxId(data["box_id"])];size = point(data["size"])
            if size.x<220 or size.y<140: raise ValueError("Рамка слишком мала")
            box.size = size;value = box;snapshot.course.saved_revision+=1
        elif name == "assign-card":
            card = snapshot.cards[CardId(data["card_id"])];box = snapshot.lecture_boxes.get(LectureBoxId(data["box_id"])) if data.get("box_id") else None
            if data.get("box_id") and not box: raise ValueError("Рамка не найдена")
            card.lecture_box_id = box.id if box else None
            note = snapshot.notes[card.note_id]
            if note.kind == NoteKind.CONCEPT: note.defined_in_lecture_note_id = box.note_id if box else None
            if box: self._fit_box(box,card)
            value = card;snapshot.course.saved_revision+=1
        elif name == "settings":
            settings = MapSettings.from_course_settings({"map":data})
            if settings.hidden_note_kinds-set(k.value for k in NoteKind): raise ValueError("Неизвестный тип карточки")
            commands.set_settings(settings);value = snapshot.course.settings
        else: raise ValueError("Неизвестное действие карты")
        self.storage.save(commands.state)
        return value

    def delete_note(self,course_id,note_id): return self._commit(course_id,lambda s:s.delete_note(NoteId(note_id)))

    def _selection(self,service,data):
        note = service._note(NoteId(data["note_id"]))
        rendered = render_markdown(note.markdown,service.state)
        return selection_from_rendered(note_id=note.id,revision=int(data["revision"]),rendered=rendered,span_index=int(data["span_index"]),rendered_start=int(data["start"]),rendered_end=int(data["end"]),selected_text=data["selected_text"])

    @serialized
    def selection_command(self,course_id,name,data):
        service = CourseService(self.storage.load(course_id))
        note = service._note(NoteId(data["note_id"]))
        if "raw_start" in data: start,end,label = checked_browser_range(note,data)
        else:
            request = self._selection(service,data)
            from selection import _checked_range
            start,end = _checked_range(service,request);label = note.markdown[start:end]
        if name == "create-note":
            kind = NoteKind(data.get("kind","concept"))
            if kind == NoteKind.LECTURE: raise ValueError("Из выделения создаётся понятие, пример или задача")
            created = Note(NoteId(str(uuid4())),service.state.course.id,kind,title_text(data["title"]),data.get("summary",""),"")
            if not isinstance(created.summary,str): raise ValueError("Описание должно быть строкой")
            lecture,box = self._lecture(service.state,data.get("lecture_note_id"))
            if lecture and kind == NoteKind.CONCEPT: created.defined_in_lecture_note_id = lecture.id
            preferred = {"x":box.position.x+25,"y":box.position.y+60} if box else data.get("position")
            card = Card(CardId(str(uuid4())),service.state.course.id,created.id,self._free_position(service.state,preferred,ignore_box=box.id if box else None),Point(220,100),box.id if box else None)
            value = service.create_note_from_selection(source_note_id=note.id,expected_revision=data["revision"],raw_start=start,raw_end=end,note=created,card=card)
            if box: self._fit_box(box,card)
        else:
            if name == "link": target = service._note(NoteId(data["target_note_id"]));url = make_internal_url("note",target.id);value = target
            elif name == "source": url = make_source_url(service,SourceId(data["source_id"]),data.get("page"));value = service.state.sources[SourceId(data["source_id"])]
            elif name == "fact":
                value = Fact(FactId(str(uuid4())),service.state.course.id,note.id,data.get("markdown",""))
                service.state.facts[value.id] = value;url = make_internal_url("fact",value.id)
            elif name == "attach-fact":
                value = service.state.facts[FactId(data["fact_id"])]
                if value.owner_note_id != note.id: raise ValueError("Факт принадлежит другому конспекту")
                url = make_internal_url("fact",value.id)
            else: raise ValueError("Неизвестное действие выделения")
            service.apply_source_patch(note.id,data["revision"],start,end,f"[{label}]({url})")
        self.storage.save(service.state)
        return value

    def edit_fact(self,course_id,fact_id,owner_note_id,markdown):
        return self._commit(course_id,lambda s:edit_fact(s,FactId(fact_id),NoteId(owner_note_id),markdown))

    @serialized
    def export_course(self,course_id): return export_course(self.storage,course_id).content

    @serialized
    def import_course(self,content): return import_course(self.storage,content).course
