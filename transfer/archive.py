"""S06 ZIP transfer.  The adapter deliberately accepts only complete v1 archives."""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import uuid
import zipfile
from math import isfinite
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Callable

from synopsis_domain.model import (
    Asset, AssetId, Card, CardId, Course, CourseId, CourseSnapshot, Edge, EdgeGeometry,
    EdgeId, EdgeKind, Fact, FactId, LectureBox, LectureBoxId, LectureSourceAttachment,
    Note, NoteId, NoteKind, Point, RelativeControlPoint, SCHEMA_VERSION, Source, SourceId,
)
from storage import FileCourseStorage, StorageError
from synopsis_domain.service import EDGE_ENDPOINTS


@dataclass(frozen=True)
class ArchiveDiagnostic:
    code: str
    message: str
    path: str | None = None


class ArchiveError(RuntimeError):
    def __init__(self, code: str, message: str, path: str | None = None):
        super().__init__(message); self.diagnostic = ArchiveDiagnostic(code, message, path)


@dataclass(frozen=True)
class ArchiveLimits:
    max_entries: int = 1_000
    max_entry_bytes: int = 32 * 1024 * 1024
    max_total_bytes: int = 256 * 1024 * 1024


@dataclass(frozen=True)
class ExportResult:
    content: bytes
    diagnostics: tuple[ArchiveDiagnostic, ...] = ()


_EXTERNAL = re.compile(r"!\[[^]]*\]\(([^)]+)\)")


def _error(code: str, message: str, path: str | None = None):
    raise ArchiveError(code, message, path)


def _safe_path(name: str) -> PurePosixPath:
    # ZIP always uses POSIX names. Backslashes are refused instead of normalized.
    p = PurePosixPath(name)
    if not name or "\\" in name or p.is_absolute() or ".." in p.parts or "." in p.parts or len(p.parts) != len(tuple(x for x in p.parts if x)):
        _error("unsafeArchive", "archive contains an unsafe path", name)
    return p


def _sha(data: bytes) -> str: return hashlib.sha256(data).hexdigest()


def _data(snapshot: CourseSnapshot) -> dict:
    def plain(value): return asdict(value)
    notes = []
    for note in snapshot.notes.values():
        item = plain(note); item.pop("markdown"); item["markdown_path"] = f"notes/{note.id}.md"; notes.append(item)
    facts = []
    for fact in snapshot.facts.values():
        item = plain(fact); item.pop("markdown"); item["markdown_path"] = f"facts/{fact.id}.md"; facts.append(item)
    assets = []
    for asset in snapshot.assets.values():
        item = plain(asset); item["archive_path"] = _asset_path(asset); assets.append(item)
    return {"course": plain(snapshot.course), "notes": notes, "cards": [plain(x) for x in snapshot.cards.values()],
            "lecture_boxes": [plain(x) for x in snapshot.lecture_boxes.values()], "edges": [plain(x) for x in snapshot.edges.values()],
            "facts": facts, "sources": [plain(x) for x in snapshot.sources.values()], "assets": assets,
            "lecture_source_attachments": [plain(x) for x in snapshot.lecture_source_attachments]}


def _asset_path(asset: Asset) -> str:
    suffix = Path(asset.original_name).suffix.lower()
    if not suffix or not re.fullmatch(r"\.[a-z0-9]{1,12}", suffix): suffix = ".bin"
    return f"assets/{asset.id}{suffix}"


def _external_diagnostics(snapshot: CourseSnapshot) -> list[ArchiveDiagnostic]:
    result = []
    for owner, markdown in [(f"notes/{n.id}.md", n.markdown) for n in snapshot.notes.values()] + [(f"facts/{f.id}.md", f.markdown) for f in snapshot.facts.values()]:
        definitions = {m.group(1).casefold(): m.group(2) for m in re.finditer(r'(?m)^ {0,3}\[([^]]+)\]:\s*(\S+)', markdown)}
        refs = _EXTERNAL.findall(markdown)
        refs += [definitions.get((label or alt).casefold(), "") for alt,label in re.findall(r'!\[([^]]*)\]\[([^]]*)\]', markdown)]
        for ref in refs:
            ref = ref.strip().strip("<>")
            if ref and not ref.startswith("synopsis://asset/"):
                result.append(ArchiveDiagnostic("externalDependency", "external image/local path is not bundled; add it as a course asset first", owner))
    return result


def export_course(storage: FileCourseStorage, course_id: str, *, limits: ArchiveLimits = ArchiveLimits()) -> ExportResult:
    snapshot = storage.load(course_id)
    if snapshot.course.schema_version != SCHEMA_VERSION: _error("unsupportedSchemaVersion", "course schema is unsupported")
    diagnostics = _external_diagnostics(snapshot)
    if diagnostics: raise ArchiveError(diagnostics[0].code, diagnostics[0].message, diagnostics[0].path)
    files: dict[str, bytes] = {"course.json": json.dumps(_data(snapshot), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()}
    for n in snapshot.notes.values(): files[f"notes/{n.id}.md"] = n.markdown.encode()
    for f in snapshot.facts.values(): files[f"facts/{f.id}.md"] = f.markdown.encode()
    for asset in snapshot.assets.values():
        _, content = storage.get_asset(course_id, asset.id)
        if len(content) != asset.byte_length or (asset.sha256 and _sha(content) != asset.sha256): _error("invalidStructure", "asset metadata does not match stored bytes", asset.id)
        files[_asset_path(asset)] = content
    _check_sizes(files, limits)
    manifest = {"format": "synopsis", "schemaVersion": SCHEMA_VERSION, "courseId": str(snapshot.course.id), "exporter": "Synopsis", "files": [{"path": p, "byteLength": len(b), "sha256": _sha(b)} for p, b in sorted(files.items())]}
    files["manifest.json"] = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for path, content in sorted(files.items()): z.writestr(path, content)
    return ExportResult(out.getvalue(), tuple(diagnostics))


def _check_sizes(files: dict[str, bytes], limits: ArchiveLimits) -> None:
    if len(files) > limits.max_entries: _error("unsafeArchive", "archive has too many files")
    total = 0
    for path, content in files.items():
        if len(content) > limits.max_entry_bytes: _error("unsafeArchive", "archive entry is too large", path)
        total += len(content)
    if total > limits.max_total_bytes: _error("unsafeArchive", "archive exceeds uncompressed size limit")


def _read_zip(content: bytes, limits: ArchiveLimits) -> dict[str, bytes]:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            infos = z.infolist()
            if len(infos) > limits.max_entries: _error("unsafeArchive", "archive has too many entries")
            names: set[str] = set(); total = 0; result = {}
            for info in infos:
                _safe_path(info.filename)
                if info.is_dir() or info.filename in names: _error("unsafeArchive", "archive has duplicate or directory entry", info.filename)
                names.add(info.filename); total += info.file_size
                if info.file_size > limits.max_entry_bytes or total > limits.max_total_bytes: _error("unsafeArchive", "archive exceeds size limits", info.filename)
                result[info.filename] = z.read(info)
            return result
    except ArchiveError: raise
    except (zipfile.BadZipFile, OSError, RuntimeError) as exc: raise ArchiveError("unsafeArchive", "archive is not a readable ZIP") from exc


def _json(files: dict[str, bytes], path: str) -> dict:
    try:
        value=json.loads(files[path])
        if not isinstance(value,dict): raise ValueError("expected an object")
        return value
    except (KeyError, UnicodeDecodeError, ValueError, TypeError) as exc: raise ArchiveError("invalidStructure", "required JSON is missing or invalid", path) from exc


def _unique(rows: list[dict], key: str, label: str) -> None:
    if any(not isinstance(x,dict) for x in rows): _error("invalidStructure", f"invalid {label} record")
    values = [x.get(key) for x in rows]
    if any(not isinstance(v, str) or not v for v in values) or len(values) != len(set(values)): _error("invalidStructure", f"duplicate or invalid {label} IDs")
    if key == "id" and any(not re.fullmatch(r"[A-Za-z0-9_-]{1,128}",v) for v in values): _error("invalidStructure", f"unsafe {label} ID")


def _snapshot(files: dict[str, bytes]) -> CourseSnapshot:
    manifest = _json(files, "manifest.json")
    if manifest.get("format") != "synopsis": _error("invalidStructure", "not a Synopsis archive", "manifest.json")
    if manifest.get("schemaVersion") != SCHEMA_VERSION: _error("unsupportedSchemaVersion", "archive schema version is unsupported", "manifest.json")
    entries = manifest.get("files")
    if not isinstance(entries, list): _error("invalidStructure", "manifest file list is invalid")
    _unique(entries, "path", "manifest path")
    expected = {x["path"] for x in entries if isinstance(x, dict) and isinstance(x.get("path"), str)}
    if expected != set(files) - {"manifest.json"}: _error("checksumMismatch", "manifest does not describe archive contents")
    for entry in entries:
        path = entry["path"]; data = files.get(path)
        if not isinstance(entry.get("byteLength"), int) or entry["byteLength"] != len(data) or entry.get("sha256") != _sha(data): _error("checksumMismatch", "archive file checksum or size differs", path)
    d = _json(files, "course.json")
    try:
        c = d["course"]; course = Course(CourseId(c["id"]), c["title"], c.get("schema_version", 1), c.get("saved_revision", 0), c.get("settings", {}))
        if course.schema_version != SCHEMA_VERSION or manifest.get("courseId") != course.id: _error("invalidStructure", "course identity/version mismatch")
        for key in ("notes", "cards", "lecture_boxes", "edges", "facts", "sources", "assets", "lecture_source_attachments"):
            if not isinstance(d.get(key), list): _error("invalidStructure", f"{key} must be a list")
        for key, label in (("notes","note"),("cards","card"),("lecture_boxes","lecture box"),("edges","edge"),("facts","fact"),("sources","source"),("assets","asset")): _unique(d[key], "id", label)
        def md(row, prefix):
            path=row.get("markdown_path");
            if path != f"{prefix}/{row['id']}.md" or path not in files: _error("invalidStructure", "markdown file is missing", str(path))
            return files[path].decode("utf-8")
        notes={NoteId(x["id"]): Note(NoteId(x["id"]),CourseId(x["course_id"]),NoteKind(x["kind"]),x["title"],x["summary"],md(x,"notes"),x.get("revision",0),NoteId(x["defined_in_lecture_note_id"]) if x.get("defined_in_lecture_note_id") else None) for x in d["notes"]}
        cards={CardId(x["id"]): Card(CardId(x["id"]),CourseId(x["course_id"]),NoteId(x["note_id"]),Point(**x["position"]),Point(**x.get("size",{"x":160,"y":72})),LectureBoxId(x["lecture_box_id"]) if x.get("lecture_box_id") else None,x.get("appearance")) for x in d["cards"]}
        boxes={LectureBoxId(x["id"]): LectureBox(LectureBoxId(x["id"]),CourseId(x["course_id"]),NoteId(x["note_id"]),Point(**x["position"]),Point(**x["size"])) for x in d["lecture_boxes"]}
        edges={EdgeId(x["id"]): Edge(EdgeId(x["id"]),CourseId(x["course_id"]),EdgeKind(x["kind"]),CardId(x["source_card_id"]),CardId(x["target_card_id"]),x.get("label"),EdgeGeometry([RelativeControlPoint(**p) for p in x.get("geometry",{}).get("control_points",[])],x.get("geometry",{}).get("routing","polyline"))) for x in d["edges"]}
        facts={FactId(x["id"]): Fact(FactId(x["id"]),CourseId(x["course_id"]),NoteId(x["owner_note_id"]),md(x,"facts")) for x in d["facts"]}
        assets={AssetId(x["id"]): Asset(AssetId(x["id"]),CourseId(x["course_id"]),x["media_type"],x["relative_path"],x["original_name"],x["byte_length"],x.get("sha256")) for x in d["assets"]}
        sources={SourceId(x["id"]): Source(SourceId(x["id"]),CourseId(x["course_id"]),x["title"],AssetId(x["asset_id"]),x.get("page_count")) for x in d["sources"]}
        attaches=[LectureSourceAttachment(NoteId(x["lecture_note_id"]),SourceId(x["source_id"]),x.get("page")) for x in d["lecture_source_attachments"]]
    except (KeyError, TypeError, ValueError, UnicodeDecodeError) as exc: raise ArchiveError("invalidStructure", "course data has invalid fields", "course.json") from exc
    snap=CourseSnapshot(course,notes,cards,boxes,edges,facts,sources,assets,attaches); _structure(snap, d, files); return snap


def _structure(s: CourseSnapshot, data: dict, files: dict[str, bytes]) -> None:
    cid=s.course.id
    groups=(s.notes,s.cards,s.lecture_boxes,s.edges,s.facts,s.sources,s.assets)
    if not isinstance(s.course.title,str) or not isinstance(s.course.settings,dict): _error("invalidStructure", "invalid course fields")
    map_settings=s.course.settings.get("map",{})
    if not isinstance(map_settings,dict) or not isinstance(map_settings.get("hiddenNoteKinds",[]),list) or not isinstance(map_settings.get("cardStyles",{}),dict) or not isinstance(map_settings.get("edgeStyles",{}),dict): _error("invalidStructure", "invalid map settings")
    if len({c.note_id for c in s.cards.values()}) != len(s.cards) or len({b.note_id for b in s.lecture_boxes.values()}) != len(s.lecture_boxes): _error("invalidStructure", "duplicate representation of a note")
    for n in s.notes.values():
        if not isinstance(n.title,str) or not isinstance(n.summary,str) or type(n.revision) is not int or n.revision < 0: _error("invalidStructure", "invalid note fields")
        if n.defined_in_lecture_note_id and (n.kind != NoteKind.CONCEPT or s.notes.get(n.defined_in_lecture_note_id) is None or s.notes[n.defined_in_lecture_note_id].kind != NoteKind.LECTURE): _error("invalidStructure", "definition target must be a lecture")
    for obj in [*s.cards.values(),*s.lecture_boxes.values()]:
        if any(type(v) not in (float,int) or not isfinite(v) or abs(v)>1e7 for v in (obj.position.x,obj.position.y,obj.size.x,obj.size.y)) or min(obj.size.x,obj.size.y)<=0: _error("invalidStructure", "invalid map geometry")
    for edge in s.edges.values():
        if edge.label is not None and not isinstance(edge.label,str): _error("invalidStructure", "invalid edge label")
        if edge.geometry.routing != "polyline" or any(type(v) not in (float,int) or not isfinite(v) for p in edge.geometry.control_points for v in (p.u,p.v)): _error("invalidStructure", "invalid edge geometry")
    if any(x.course_id != cid for group in groups for x in group.values()): _error("courseMismatch", "entity belongs to a different course")
    if any(card.note_id not in s.notes or (card.lecture_box_id and card.lecture_box_id not in s.lecture_boxes) for card in s.cards.values()): _error("invalidStructure", "card reference is missing")
    if any(s.notes[c.note_id].kind==NoteKind.LECTURE for c in s.cards.values()): _error("invalidStructure", "lecture requires a box, not an ordinary card")
    if any(box.note_id not in s.notes for box in s.lecture_boxes.values()) or any(box.note_id not in s.notes or s.notes[box.note_id].kind != NoteKind.LECTURE for box in s.lecture_boxes.values()): _error("invalidStructure", "lecture box must own a lecture note")
    if any(n.defined_in_lecture_note_id and n.defined_in_lecture_note_id not in s.notes for n in s.notes.values()): _error("invalidStructure", "definition lecture is missing")
    if any(f.owner_note_id not in s.notes for f in s.facts.values()): _error("invalidStructure", "fact owner is missing")
    for edge in s.edges.values():
        if edge.source_card_id not in s.cards or edge.target_card_id not in s.cards or edge.source_card_id == edge.target_card_id: _error("invalidEdge", "edge endpoints are invalid")
        source = s.notes[s.cards[edge.source_card_id].note_id].kind
        target = s.notes[s.cards[edge.target_card_id].note_id].kind
        if (source, target) != EDGE_ENDPOINTS[edge.kind]: _error("invalidEdge", "edge endpoints do not match edge kind")
    if any(src.asset_id not in s.assets for src in s.sources.values()): _error("invalidStructure", "source asset is missing")
    for source in s.sources.values():
        if s.assets[source.asset_id].media_type != "application/pdf" or (source.page_count is not None and (type(source.page_count) is not int or source.page_count<1)): _error("invalidStructure", "invalid PDF source")
    for attachment in s.lecture_source_attachments:
        if attachment.lecture_note_id not in s.notes or attachment.source_id not in s.sources: _error("invalidStructure", "source reference is missing")
        if s.notes[attachment.lecture_note_id].kind != NoteKind.LECTURE: _error("invalidStructure", "source must attach to a lecture")
        pages = s.sources[attachment.source_id].page_count
        if attachment.page is not None and (not isinstance(attachment.page, int) or attachment.page < 1 or (pages is not None and attachment.page > pages)): _error("invalidStructure", "source page is invalid")
    asset_rows={x["id"]:x for x in data["assets"]}
    for aid, asset in s.assets.items():
        if asset.relative_path != asset.id: _error("unsafeArchive", "asset storage path must be its stable ID")
        if asset.media_type not in {"application/pdf","image/png","image/jpeg","image/gif","image/webp","image/avif"}: _error("invalidStructure", "unsupported attachment media type")
        path=asset_rows[str(aid)].get("archive_path")
        if path != _asset_path(asset) or path not in files or len(files[path]) != asset.byte_length or (asset.sha256 and _sha(files[path]) != asset.sha256): _error("invalidStructure", "asset bytes are missing or invalid", str(path))


def import_course(storage: FileCourseStorage, content: bytes, *, limits: ArchiveLimits = ArchiveLimits()) -> CourseSnapshot:
    # Everything through validation happens in memory; only a valid independent copy is staged.
    files=_read_zip(content, limits)
    snap=_snapshot(files)
    new_id=CourseId(str(uuid.uuid4()))
    snap.course.id=new_id
    for group in (snap.notes,snap.cards,snap.lecture_boxes,snap.edges,snap.facts,snap.sources,snap.assets):
        for value in group.values(): value.course_id=new_id
    # Do not use tempfile here: the Windows sandbox can create a directory whose
    # ACL denies the child process. This is a single, UUID-named staging target.
    stage=storage.root / ("synopsis-import-" + uuid.uuid4().hex)
    stage.mkdir(parents=False, exist_ok=False)
    published_assets: Path | None = None
    try:
        staged=FileCourseStorage(stage)
        staged.save(snap)
        for asset in snap.assets.values():
            # bytes were verified above; stage exactly the archive bytes.
            # metadata exists in the staged snapshot already, so write directly atomically.
            source_data = files[_asset_path(asset)]
            folder=staged.assets / str(new_id); folder.mkdir(exist_ok=True)
            (folder / asset.relative_path).write_bytes(source_data)
        # Publish course JSON only after complete staging. Asset directory rename is atomic within root.
        target_assets=storage.assets / str(new_id)
        if snap.assets:
            os.replace(staged.assets / str(new_id), target_assets)
            published_assets=target_assets
        os.replace(staged._course_path(str(new_id)), storage._course_path(str(new_id)))
        return storage.load(str(new_id))
    except ArchiveError: raise
    except (OSError, StorageError) as exc: raise ArchiveError("courseConflict", "could not publish imported course; existing data is unchanged") from exc
    finally:
        # A new UUID makes this exact directory ours; remove it only if the course
        # JSON did not publish, so failed imports leave no reachable partial course.
        if published_assets is not None and not storage._course_path(str(new_id)).exists():
            shutil.rmtree(published_assets, ignore_errors=True)
        shutil.rmtree(stage, ignore_errors=True)
