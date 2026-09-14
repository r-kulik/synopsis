"""Validated authoring commands. Models never write the archive schema or IDs."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from functools import wraps
from hashlib import sha256
from pathlib import Path
import os
import re
import shutil
from threading import RLock
from uuid import uuid4

from storage import FileCourseStorage
from synopsis_domain import (
    Asset, Card, Course, CourseService, CourseSnapshot, Edge, EdgeKind, Fact,
    LectureBox, LectureSourceAttachment, Note, NoteKind, Point, Source,
    make_internal_url, parse_internal_url,
)
from transfer import export_course, import_course
from transfer.archive import ArchiveLimits, _read_zip, _snapshot


def text(value, label, limit=200_000, empty=False):
    if not isinstance(value, str) or len(value) > limit or (not empty and not value.strip()):
        raise ValueError(f"{label}: expected {'a' if empty else 'a nonempty'} string, at most {limit} characters")
    return value


def positive(value, label):
    if type(value) is not int or value < 1:
        raise ValueError(f"{label}: expected a positive integer")
    return value


def serialized(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return call


@contextmanager
def workspace_lock(root):
    """OS-owned lock: a crash releases it; a second MCP writer is rejected."""
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    with (root / 'writer.lock').open('a+b') as handle:
        handle.seek(0, os.SEEK_END)
        if not handle.tell():
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


class AuthoringWorkspace:
    def __init__(self, root, input_roots=()):
        self.root = Path(root).resolve()
        if self.root.name == '.synopsis-data':
            raise ValueError('Use a separate MCP workspace, never .synopsis-data')
        self.storage = FileCourseStorage(self.root / 'drafts')
        self.exports = self.root / 'exports'
        self.exports.mkdir(parents=True, exist_ok=True)
        default_inputs = self.root / 'inputs'
        default_inputs.mkdir(exist_ok=True)
        self.input_roots = [default_inputs.resolve(), *[Path(p).resolve() for p in input_roots]]
        self._lock = RLock()

    def _load(self, course_id):
        return self.storage.load(course_id)

    @staticmethod
    def _meta(snapshot):
        return snapshot.course.settings['authoring']

    @staticmethod
    def _note(snapshot, note_id):
        if note_id not in snapshot.notes:
            raise ValueError('Note does not exist in this course; use get_course to recover IDs')
        return snapshot.notes[note_id]

    def _citations(self, snapshot, citations):
        if not isinstance(citations, list) or not citations:
            raise ValueError('Provide at least one citation to a registered presentation')
        result = []
        presentations = self._meta(snapshot)['presentations']
        for row in citations:
            if not isinstance(row, dict) or set(row) - {'presentation_id', 'start_slide', 'end_slide'}:
                raise ValueError('Invalid citation fields')
            pid = row.get('presentation_id')
            if pid not in presentations:
                raise ValueError('Unknown presentation_id in this course')
            start = positive(row.get('start_slide'), 'start_slide')
            end = positive(row.get('end_slide', start), 'end_slide')
            if end < start or end > presentations[pid]['slide_count']:
                raise ValueError('Citation is outside the registered slide range')
            result.append({'presentation_id': pid, 'start_slide': start, 'end_slide': end})
        return result

    def _citation_suffix(self, snapshot, citations):
        rows = []
        for c in citations:
            p = self._meta(snapshot)['presentations'][c['presentation_id']]
            # Plain inline code prevents filenames being interpreted as Markdown links.
            filename = p['filename'].replace('`', '').replace('\n', ' ')
            rows.append(f"- `{filename}` · слайды {c['start_slide']}–{c['end_slide']}")
        return '\n\n### Исходные слайды\n\n' + '\n'.join(rows)

    @staticmethod
    def _check_links(snapshot):
        service = CourseService(snapshot)
        for owner, markdown in [(n.id, n.markdown) for n in snapshot.notes.values()] + [(f.owner_note_id, f.markdown) for f in snapshot.facts.values()]:
            for raw in re.findall(r'synopsis://[^\s)\]<>`]+', markdown):
                address = parse_internal_url(raw)
                if address is None or service.resolve_internal_url(raw) is None:
                    raise ValueError(f'Unresolved or invalid internal link: {raw}')
                if address.resource == 'fact' and snapshot.facts[address.id].owner_note_id != owner:
                    raise ValueError('A fact may only be linked from its owner note')

    def _archive(self, snapshot, pending=None):
        self._check_links(snapshot)
        storage = self.storage
        pending = pending or {}

        class View:
            def load(self, course_id):
                return snapshot

            def get_asset(self, course_id, asset_id):
                if asset_id in pending:
                    return snapshot.assets[asset_id], pending[asset_id]
                return storage.get_asset(course_id, asset_id)

        content = export_course(View(), snapshot.course.id).content
        # Use the very same structural validator as real import before committing.
        _snapshot(_read_zip(content, ArchiveLimits()))
        return content

    def _commit(self, snapshot, pending=None):
        snapshot.course.saved_revision += 1
        self._archive(snapshot, pending)
        created = []
        try:
            for aid, content in (pending or {}).items():
                asset = snapshot.assets[aid]
                self.storage.put_asset(snapshot.course.id, aid, asset.original_name, asset.media_type, content)
                created.append(self.storage.assets / snapshot.course.id / aid)
            self.storage.save(snapshot)
        except Exception:
            # Only this call's new UUID assets, never an existing user asset.
            for path in created:
                path.unlink(missing_ok=True)
            raise

    @staticmethod
    def _layout(snapshot):
        boxes = list(snapshot.lecture_boxes.values())
        y = 120
        for row in range(0, len(boxes), 2):
            heights = []
            for col, box in enumerate(boxes[row:row + 2]):
                cards = [c for c in snapshot.cards.values() if c.lecture_box_id == box.id]
                height = max(240, 100 + ((len(cards) + 2) // 3) * 135)
                box.position = Point(60 + col * 880, y)
                box.size = Point(790, height)
                for i, card in enumerate(cards):
                    card.position = Point(box.position.x + 30 + i % 3 * 250, y + 70 + i // 3 * 135)
                heights.append(height)
            y += max(heights) + 100
        for i, card in enumerate(c for c in snapshot.cards.values() if c.lecture_box_id is None):
            card.position = Point(90 + i % 6 * 250, y + i // 6 * 135)

    @serialized
    def create_course(self, title):
        snapshot = CourseSnapshot(Course(str(uuid4()), text(title, 'title', 500).strip()))
        snapshot.course.settings['authoring'] = {'version': 1, 'presentations': {}, 'citations': {}}
        self._commit(snapshot)
        return {'course_id': snapshot.course.id, 'title': snapshot.course.title}

    @serialized
    def list_courses(self):
        return [{'course_id': c.id, 'title': c.title} for c in self.storage.list_courses()]

    @serialized
    def register_presentation(self, course_id, filename, slide_count, title=''):
        snapshot = self._load(course_id)
        filename = text(filename, 'filename', 500).strip()
        positive(slide_count, 'slide_count')
        if slide_count > 10_000:
            raise ValueError('At most 10000 slides per registered presentation')
        items = self._meta(snapshot)['presentations']
        for pid, item in items.items():
            if item['filename'] == filename:
                if item['slide_count'] != slide_count:
                    raise ValueError('Presentation already registered with a different slide count')
                return {'presentation_id': pid, **item}
        pid = str(uuid4())
        item = {'filename': filename, 'slide_count': slide_count, 'title': text(title, 'title', 500, empty=True)}
        items[pid] = item
        self._commit(snapshot)
        return {'presentation_id': pid, **item}

    @serialized
    def add_note(self, course_id, kind, title, markdown, citations, lecture_id=None, summary=''):
        snapshot = self._load(course_id)
        kind = NoteKind(kind)
        title = text(title, 'title', 500).strip()
        text(markdown, 'markdown', empty=True)
        text(summary, 'summary', 1000, empty=True)
        for n in snapshot.notes.values():
            if n.kind == kind and n.title.casefold() == title.casefold():
                raise ValueError(f'Note with this title/type exists: {n.id}. Reuse it or clarify the title')
        evidence = self._citations(snapshot, citations)
        box = None
        if lecture_id is not None:
            if kind == NoteKind.LECTURE or self._note(snapshot, lecture_id).kind != NoteKind.LECTURE:
                raise ValueError('lecture_id must reference a lecture; lectures cannot be nested')
            box = next(b for b in snapshot.lecture_boxes.values() if b.note_id == lecture_id)
        note = Note(str(uuid4()), course_id, kind, title, summary,
                    markdown + self._citation_suffix(snapshot, evidence),
                    defined_in_lecture_note_id=lecture_id if kind == NoteKind.CONCEPT else None)
        snapshot.notes[note.id] = note
        self._meta(snapshot)['citations'][note.id] = evidence
        if kind == NoteKind.LECTURE:
            item = LectureBox(str(uuid4()), course_id, note.id, Point(0, 0), Point(790, 240))
            snapshot.lecture_boxes[item.id] = item
        else:
            item = Card(str(uuid4()), course_id, note.id, Point(0, 0), Point(220, 100), box.id if box else None)
            snapshot.cards[item.id] = item
        self._layout(snapshot)
        self._commit(snapshot)
        return self.get_note(course_id, note.id)

    @serialized
    def get_note(self, course_id, note_id):
        snapshot = self._load(course_id)
        note = self._note(snapshot, note_id)
        citations = self._meta(snapshot)['citations'][note.id]
        suffix = self._citation_suffix(snapshot, citations)
        return {**asdict(note), 'url': make_internal_url('note', note.id), 'citations': citations,
                'body': note.markdown.removesuffix(suffix)}

    @serialized
    def update_note(self, course_id, note_id, markdown, expected_revision, citations=None):
        snapshot = self._load(course_id)
        note = self._note(snapshot, note_id)
        if type(expected_revision) is not int or note.revision != expected_revision:
            raise ValueError('Stale revision. Call get_note and preserve intervening changes')
        text(markdown, 'markdown', empty=True)
        evidence = self._citations(snapshot, citations) if citations is not None else self._meta(snapshot)['citations'][note.id]
        note.markdown = markdown + self._citation_suffix(snapshot, evidence)
        note.revision += 1
        self._meta(snapshot)['citations'][note.id] = evidence
        self._commit(snapshot)
        return self.get_note(course_id, note_id)

    @serialized
    def add_fact(self, course_id, owner_note_id, markdown, citations, label='Пояснение'):
        snapshot = self._load(course_id)
        owner = self._note(snapshot, owner_note_id)
        text(markdown, 'markdown')
        label = text(label, 'label', 200)
        if any(c in label for c in '[]\n\r'):
            raise ValueError('Fact label must be plain single-line text without brackets')
        evidence = self._citations(snapshot, citations)
        fact = Fact(str(uuid4()), course_id, owner.id, markdown + self._citation_suffix(snapshot, evidence))
        CourseService(snapshot).create_fact(fact)
        self._meta(snapshot)['citations'][fact.id] = evidence
        # Insert a safe link automatically; a fact never becomes an orphan comment.
        suffix = self._citation_suffix(snapshot, self._meta(snapshot)['citations'][owner.id])
        url = make_internal_url('fact', fact.id)
        owner.markdown = owner.markdown.removesuffix(suffix) + f'\n\n[{label}]({url})' + suffix
        owner.revision += 1
        self._commit(snapshot)
        return {'fact_id': fact.id, 'owner_note_id': owner.id, 'url': url, 'owner_revision': owner.revision}

    @serialized
    def connect(self, course_id, source_note_id, target_note_id, kind, label):
        snapshot = self._load(course_id)
        text(label, 'label', 500)
        self._note(snapshot, source_note_id)
        self._note(snapshot, target_note_id)
        cards = {c.note_id: c for c in snapshot.cards.values()}
        if source_note_id not in cards or target_note_id not in cards:
            raise ValueError('Only ordinary note cards can be connected, not lecture frames')
        kind = EdgeKind(kind)
        source, target = cards[source_note_id].id, cards[target_note_id].id
        for edge in snapshot.edges.values():
            if (edge.source_card_id, edge.target_card_id, edge.kind) == (source, target, kind):
                return asdict(edge)
        edge = Edge(str(uuid4()), course_id, kind, source, target, label)
        CourseService(snapshot).create_edge(edge)
        self._commit(snapshot)
        return asdict(edge)

    @serialized
    def attach_file(self, course_id, path, lecture_id=None):
        snapshot = self._load(course_id)
        target = Path(path)
        if not target.is_absolute():
            target = self.input_roots[0] / target
        target = target.resolve()
        if not any(target.is_relative_to(root) for root in self.input_roots) or not target.is_file():
            raise ValueError('File must be inside an explicitly allowed input directory')
        if lecture_id is not None and self._note(snapshot, lecture_id).kind != NoteKind.LECTURE:
            raise ValueError('Only a lecture can own a PDF attachment')
        if not 0 < target.stat().st_size <= 32 * 1024 * 1024:
            raise ValueError('Attachment must be nonempty and at most 32 MiB')
        media = {'.pdf': 'application/pdf', '.png': 'image/png', '.jpg': 'image/jpeg',
                 '.jpeg': 'image/jpeg', '.webp': 'image/webp'}.get(target.suffix.lower())
        if not media:
            raise ValueError('Supported: PDF, PNG, JPEG, WebP. Convert PPTX to PDF first')
        content = target.read_bytes()
        pages = None
        if media == 'application/pdf':
            from io import BytesIO
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(content), strict=True)
            if reader.is_encrypted:
                raise ValueError('Encrypted PDF is not supported')
            pages = positive(len(reader.pages), 'PDF page count')
        else:
            valid = ((media == 'image/png' and content.startswith(b'\x89PNG\r\n\x1a\n'))
                     or (media == 'image/jpeg' and content.startswith(b'\xff\xd8\xff'))
                     or (media == 'image/webp' and content[:4] == b'RIFF' and content[8:12] == b'WEBP'))
            if not valid:
                raise ValueError('Image signature does not match its extension')
            if lecture_id is not None:
                raise ValueError('Use the returned asset URL in Markdown for an image')
        aid = str(uuid4())
        asset = Asset(aid, course_id, media, aid, target.name, len(content), sha256(content).hexdigest())
        snapshot.assets[aid] = asset
        result = {'asset_id': aid, 'url': make_internal_url('asset', aid), 'media_type': media}
        if pages is not None:
            sid = str(uuid4())
            snapshot.sources[sid] = Source(sid, course_id, target.name, aid, pages)
            if lecture_id is not None:
                snapshot.lecture_source_attachments.append(LectureSourceAttachment(lecture_id, sid))
            result.update(source_id=sid, page_count=pages, url=make_internal_url('source', sid))
        self._commit(snapshot, {aid: content})
        return result

    @serialized
    def get_course(self, course_id):
        snapshot = self._load(course_id)
        return {'course_id': course_id, 'title': snapshot.course.title,
                'revision': snapshot.course.saved_revision,
                'presentations': self._meta(snapshot)['presentations'],
                'notes': [{'id': n.id, 'title': n.title, 'kind': n.kind, 'revision': n.revision,
                           'url': make_internal_url('note', n.id)} for n in snapshot.notes.values()],
                'edges': [asdict(e) for e in snapshot.edges.values()],
                'sources': [asdict(s) for s in snapshot.sources.values()],
                'facts': [asdict(f) for f in snapshot.facts.values()]}

    @serialized
    def validate_course(self, course_id):
        snapshot = self._load(course_id)
        self._archive(snapshot)
        missing = []
        used = {p: set() for p in self._meta(snapshot)['presentations']}
        for citations in self._meta(snapshot)['citations'].values():
            for c in citations:
                used[c['presentation_id']].update(range(c['start_slide'], c['end_slide'] + 1))
        for pid, item in self._meta(snapshot)['presentations'].items():
            slides = [i for i in range(1, item['slide_count'] + 1) if i not in used[pid]]
            if slides:
                missing.append({'presentation_id': pid, 'filename': item['filename'], 'uncited_slides': slides})
        return {'valid_structure': True, 'notes': len(snapshot.notes), 'lectures': len(snapshot.lecture_boxes),
                'cards': len(snapshot.cards), 'edges': len(snapshot.edges), 'coverage_warnings': missing,
                'content_accuracy': 'not verified by software'}

    @serialized
    def export_course(self, course_id):
        snapshot = self._load(course_id)
        report = self.validate_course(course_id)
        if not snapshot.notes or not snapshot.lecture_boxes:
            raise ValueError('Create at least one lecture before exporting a study course')
        content = self._archive(snapshot)
        check_root = self.root / ('check-' + uuid4().hex)
        check_root.mkdir()
        try:
            imported = import_course(FileCourseStorage(check_root), content)
            if set(imported.notes) != set(snapshot.notes):
                raise ValueError('Round-trip note identities differ')
        finally:
            shutil.rmtree(check_root)
        target = self.exports / f'{course_id}-r{snapshot.course.saved_revision}.synopsis'
        if target.exists():
            # Retries are harmless; do not replace an existing export.
            if target.read_bytes() != content:
                # ZIP timestamps may differ: compare unpacked verified contents.
                if _read_zip(target.read_bytes(), ArchiveLimits()) != _read_zip(content, ArchiveLimits()):
                    raise ValueError('An export with this revision already exists with different contents')
        else:
            with target.open('xb') as stream:
                try:
                    stream.write(content)
                except Exception:
                    stream.close()
                    target.unlink(missing_ok=True)
                    raise
        return {'path': str(target), 'bytes': target.stat().st_size, 'round_trip': True, **report}
