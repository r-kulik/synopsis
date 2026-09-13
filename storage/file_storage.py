"""Durable, course-scoped file storage for the S01 CourseSnapshot contract."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict
from pathlib import Path

from synopsis_domain.model import (
    Asset, AssetId, Card, CardId, Course, CourseId, CourseSnapshot, Edge, EdgeGeometry,
    EdgeId, EdgeKind, Fact, FactId, LectureBox, LectureBoxId, LectureSourceAttachment,
    Note, NoteId, NoteKind, Point, RelativeControlPoint, Source, SourceId,
)


class StorageError(RuntimeError): pass
class StorageWriteError(StorageError): pass


def _snapshot_to_data(s: CourseSnapshot) -> dict:
    def item(value):
        data = asdict(value)
        # StrEnum and NewType values are JSON scalars once asdict has recursed.
        return data
    return {"course": item(s.course), "notes": [item(x) for x in s.notes.values()],
            "cards": [item(x) for x in s.cards.values()], "lecture_boxes": [item(x) for x in s.lecture_boxes.values()],
            "edges": [item(x) for x in s.edges.values()], "facts": [item(x) for x in s.facts.values()],
            "sources": [item(x) for x in s.sources.values()], "assets": [item(x) for x in s.assets.values()],
            "lecture_source_attachments": [item(x) for x in s.lecture_source_attachments]}


def _snapshot_from_data(d: dict) -> CourseSnapshot:
    try:
        c = d["course"]; course = Course(CourseId(c["id"]), c["title"], c.get("schema_version", 1), c.get("saved_revision", 0), c.get("settings", {}))
        notes = {NoteId(x["id"]): Note(NoteId(x["id"]), CourseId(x["course_id"]), NoteKind(x["kind"]), x["title"], x["summary"], x["markdown"], x.get("revision", 0), NoteId(x["defined_in_lecture_note_id"]) if x.get("defined_in_lecture_note_id") else None) for x in d["notes"]}
        cards = {CardId(x["id"]): Card(CardId(x["id"]), CourseId(x["course_id"]), NoteId(x["note_id"]), Point(**x["position"]), Point(**x.get("size", {"x":160,"y":72})), LectureBoxId(x["lecture_box_id"]) if x.get("lecture_box_id") else None, x.get("appearance")) for x in d["cards"]}
        boxes = {LectureBoxId(x["id"]): LectureBox(LectureBoxId(x["id"]), CourseId(x["course_id"]), NoteId(x["note_id"]), Point(**x["position"]), Point(**x["size"])) for x in d["lecture_boxes"]}
        edges = {EdgeId(x["id"]): Edge(EdgeId(x["id"]), CourseId(x["course_id"]), EdgeKind(x["kind"]), CardId(x["source_card_id"]), CardId(x["target_card_id"]), x.get("label"), EdgeGeometry([RelativeControlPoint(**p) for p in x.get("geometry", {}).get("control_points", [])], x.get("geometry", {}).get("routing", "polyline"))) for x in d["edges"]}
        facts = {FactId(x["id"]): Fact(FactId(x["id"]), CourseId(x["course_id"]), NoteId(x["owner_note_id"]), x["markdown"]) for x in d["facts"]}
        assets = {AssetId(x["id"]): Asset(AssetId(x["id"]), CourseId(x["course_id"]), x["media_type"], x["relative_path"], x["original_name"], x["byte_length"], x.get("sha256")) for x in d["assets"]}
        sources = {SourceId(x["id"]): Source(SourceId(x["id"]), CourseId(x["course_id"]), x["title"], AssetId(x["asset_id"]), x.get("page_count")) for x in d["sources"]}
        attachments = [LectureSourceAttachment(NoteId(x["lecture_note_id"]), SourceId(x["source_id"]), x.get("page")) for x in d["lecture_source_attachments"]]
        return CourseSnapshot(course, notes, cards, boxes, edges, facts, sources, assets, attachments)
    except (KeyError, TypeError, ValueError) as exc:
        raise StorageError("invalid saved course snapshot") from exc


class FileCourseStorage:
    """One JSON snapshot per course; replace makes a failed write leave the old file intact."""
    def __init__(self, root: Path | str):
        self.root = Path(root); self.courses = self.root / "courses"; self.assets = self.root / "assets"
        self.courses.mkdir(parents=True, exist_ok=True); self.assets.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_id(value: str) -> str:
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
            raise StorageError("invalid entity id")
        return value

    def _course_path(self, course_id: str) -> Path:
        return self.courses / f"{self._safe_id(course_id)}.json"
    def list_courses(self) -> list[Course]:
        result = []
        for path in self.courses.glob("*.json"):
            result.append(self.load(path.stem).course)
        return sorted(result, key=lambda c: c.title.casefold())
    def load(self, course_id: str) -> CourseSnapshot:
        try:
            with self._course_path(course_id).open(encoding="utf-8") as f: return _snapshot_from_data(json.load(f))
        except FileNotFoundError: raise StorageError("course does not exist")
        except json.JSONDecodeError as exc: raise StorageError("saved course is not valid JSON") from exc
    def save(self, snapshot: CourseSnapshot) -> None:
        target = self._course_path(snapshot.course.id); fd = None; temp = None
        try:
            fd, temp = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=self.courses)
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                fd = None; json.dump(_snapshot_to_data(snapshot), f, ensure_ascii=False, sort_keys=True); f.flush(); os.fsync(f.fileno())
            os.replace(temp, target); temp = None
        except OSError as exc: raise StorageWriteError("could not persist course; previous saved version is unchanged") from exc
        finally:
            if fd is not None: os.close(fd)
            if temp:
                try: os.unlink(temp)
                except OSError: pass
    def put_asset(self, course_id: str, asset_id: str, original_name: str, media_type: str, content: bytes) -> Asset:
        self._safe_id(asset_id)
        self.load(course_id)  # course must exist before any file is accepted
        folder = self.assets / course_id; folder.mkdir(exist_ok=True)
        target = folder / asset_id; fd, temp = tempfile.mkstemp(prefix=asset_id + ".", suffix=".tmp", dir=folder)
        try:
            with os.fdopen(fd, "wb") as f: f.write(content); f.flush(); os.fsync(f.fileno())
            os.replace(temp, target)
        except OSError as exc: raise StorageWriteError("could not persist asset") from exc
        return Asset(AssetId(asset_id), CourseId(course_id), media_type, asset_id, original_name, len(content), hashlib.sha256(content).hexdigest())
    def get_asset(self, course_id: str, asset_id: str) -> tuple[Asset, bytes]:
        self._safe_id(asset_id)
        snapshot = self.load(course_id)
        asset = snapshot.assets.get(AssetId(asset_id))
        if asset is None or asset.course_id != CourseId(course_id): raise StorageError("asset does not exist in this course")
        folder = (self.assets / course_id).resolve()
        target = (folder / asset.relative_path).resolve()
        if not target.is_relative_to(folder): raise StorageError("invalid asset path")
        try: return asset, target.read_bytes()
        except OSError as exc: raise StorageError("asset bytes are unavailable") from exc
