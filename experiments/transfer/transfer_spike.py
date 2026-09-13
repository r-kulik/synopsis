#!/usr/bin/env python3
"""S00-C only: a stdlib proof that a .synopsis ZIP can be self-contained."""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import uuid
import zipfile
from pathlib import Path, PurePosixPath

SCHEMA = 1
PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cfc0000004010100f8ff030000000049454e44ae426082")
PDF = b"%PDF-1.4\n% S00 transfer fixture\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


class ImportErrorForSpike(Exception):
    pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def fixture(storage: Path) -> dict:
    """Create a tiny course where a standalone Note has no Card."""
    course = {
        "id": "course-linear-algebra", "title": "Linear algebra spike", "schemaVersion": SCHEMA,
        "settings": {"visibility": {"externalConcept": False}, "styles": {"concept": {"color": "#336699"}}},
        "notes": [
            {"id": "note-card", "kind": "concept", "title": "Matrix", "summary": "Rectangular array", "markdownPath": "notes/note-card.md"},
            {"id": "note-standalone", "kind": "example", "title": "No card", "summary": "Deliberately cardless", "markdownPath": "notes/note-standalone.md"},
        ],
        "cards": [{"id": "card-matrix", "noteId": "note-card", "position": {"x": 10, "y": 20}}],
        "facts": [{"id": "fact-matrix", "ownerNoteId": "note-card", "markdown": "Fact: determinant changes under row swaps."}],
        "assets": [
            {"id": "asset-pdf", "mediaType": "application/pdf", "relativePath": "assets/source.pdf"},
            {"id": "asset-image", "mediaType": "image/png", "relativePath": "assets/diagram.png"},
        ],
        "sources": [{"id": "source-lecture", "assetId": "asset-pdf", "title": "fixture.pdf"}],
        "lectureSourceAttachments": [], "edges": [],
    }
    write_json(storage / "course.json", course)
    (storage / "notes").mkdir(parents=True)
    (storage / "assets").mkdir(parents=True)
    (storage / "notes" / "note-card.md").write_text("Matrix. ![diagram](../assets/diagram.png)\n", encoding="utf-8")
    # This is intentionally a valid textual link now; delete_note makes it dangling.
    (storage / "notes" / "note-standalone.md").write_text("See [Matrix](synopsis://note/note-card).\n", encoding="utf-8")
    (storage / "assets" / "source.pdf").write_bytes(PDF)
    (storage / "assets" / "diagram.png").write_bytes(PNG)
    return course


def remove_card(storage: Path, card_id: str) -> None:
    course = read_json(storage / "course.json")
    course["cards"] = [x for x in course["cards"] if x["id"] != card_id]
    write_json(storage / "course.json", course)


def delete_note(storage: Path, note_id: str) -> None:
    course = read_json(storage / "course.json")
    course["notes"] = [x for x in course["notes"] if x["id"] != note_id]
    course["cards"] = [x for x in course["cards"] if x["noteId"] != note_id]
    course["facts"] = [x for x in course["facts"] if x["ownerNoteId"] != note_id]
    write_json(storage / "course.json", course)
    (storage / "notes" / (note_id + ".md")).unlink()


def export_course(storage: Path, archive: Path) -> None:
    course = read_json(storage / "course.json")
    paths = ["course.json"] + [n["markdownPath"] for n in course["notes"]] + [a["relativePath"] for a in course["assets"]]
    entries = []
    for name in paths:
        data = (storage / name).read_bytes()
        entries.append({"path": name, "byteLength": len(data), "sha256": sha(data)})
    manifest = {"format": "synopsis", "schemaVersion": SCHEMA, "courseId": course["id"], "files": entries}
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, sort_keys=True))
        for name in paths:
            z.write(storage / name, arcname=name)


def safe_member(name: str) -> bool:
    p = PurePosixPath(name)
    return not p.is_absolute() and ".." not in p.parts and "\\" not in name and name not in ("", ".")


def validate_archive(archive: Path) -> tuple[zipfile.ZipFile, dict]:
    try:
        z = zipfile.ZipFile(archive)
    except (OSError, zipfile.BadZipFile) as e:
        raise ImportErrorForSpike("invalid ZIP") from e
    names = z.namelist()
    if len(names) != len(set(names)) or any(not safe_member(n) for n in names):
        z.close(); raise ImportErrorForSpike("unsafe ZIP entries")
    try:
        manifest = json.loads(z.read("manifest.json"))
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as e:
        z.close(); raise ImportErrorForSpike("invalid manifest") from e
    if manifest.get("format") != "synopsis" or manifest.get("schemaVersion") != SCHEMA:
        z.close(); raise ImportErrorForSpike("unsupported manifest")
    listed = manifest.get("files")
    if not isinstance(listed, list) or {x.get("path") for x in listed if isinstance(x, dict)} | {"manifest.json"} != set(names):
        z.close(); raise ImportErrorForSpike("manifest file set mismatch")
    for entry in listed:
        if not isinstance(entry, dict) or not safe_member(entry.get("path", "")):
            z.close(); raise ImportErrorForSpike("invalid manifest entry")
        data = z.read(entry["path"])
        if entry.get("byteLength") != len(data) or entry.get("sha256") != sha(data):
            z.close(); raise ImportErrorForSpike("attachment checksum mismatch")
    try:
        course = json.loads(z.read("course.json"))
        note_ids = [x["id"] for x in course["notes"]]
        card_notes = [x["noteId"] for x in course["cards"]]
        if len(note_ids) != len(set(note_ids)) or any(x not in note_ids for x in card_notes): raise ValueError
        for n in course["notes"]: z.getinfo(n["markdownPath"])
        for a in course["assets"]: z.getinfo(a["relativePath"])
        if any(f["ownerNoteId"] not in note_ids for f in course["facts"]): raise ValueError
    except (KeyError, TypeError, ValueError, zipfile.BadZipFile) as e:
        z.close(); raise ImportErrorForSpike("invalid course structure") from e
    return z, course


def import_course(archive: Path, destination: Path) -> None:
    """Validate completely, extract to a sibling staging dir, then publish once."""
    z, course = validate_archive(archive)
    staging = destination.parent / ("synopsis-import-staging-" + uuid.uuid4().hex)
    staging.mkdir()
    try:
        z.extractall(staging)
        write_json(staging / "imported.json", {"courseId": course["id"]})
        if destination.exists(): raise ImportErrorForSpike("destination already exists")
        staging.replace(destination)
    finally:
        z.close()
        if staging.exists(): shutil.rmtree(staging)


def assert_bytes(left: Path, right: Path, rel: str) -> None:
    if (left / rel).read_bytes() != (right / rel).read_bytes(): raise AssertionError("bytes differ: " + rel)


def main() -> int:
    # A unique child avoids touching a prior failed run. It is the only tree
    # this script removes; source and import are separate children.
    work = Path(__file__).resolve().parent / ("transfer-spike-work-" + uuid.uuid4().hex)
    work.mkdir()
    try:
        source, imported, malformed_target = work / "source", work / "clean-import", work / "existing-storage"
        fixture(source)
        # RemoveCard preserves Note, Fact, links and attachments.
        remove_card(source, "card-matrix")
        c = read_json(source / "course.json")
        assert not c["cards"] and c["facts"][0]["ownerNoteId"] == "note-card"
        assert (source / "notes" / "note-card.md").exists() and (source / "assets" / "source.pdf").exists()
        # Restore the map representation only for a rich exported snapshot.
        c["cards"] = [{"id": "card-matrix-restored", "noteId": "note-card", "position": {"x": 10, "y": 20}}]; write_json(source / "course.json", c)
        archive = work / "course.synopsis"; export_course(source, archive); import_course(archive, imported)
        imported_course = read_json(imported / "course.json")
        assert any(n["id"] == "note-standalone" for n in imported_course["notes"])
        assert not any(x["noteId"] == "note-standalone" for x in imported_course["cards"])
        assert imported_course["facts"] and imported_course["settings"] == read_json(source / "course.json")["settings"]
        assert_bytes(source, imported, "assets/source.pdf"); assert_bytes(source, imported, "assets/diagram.png")
        # Deleting a Note leaves another Note's Markdown unchanged; its textual target is now invalid but permitted.
        delete_note(imported, "note-card")
        assert "synopsis://note/note-card" in (imported / "notes" / "note-standalone.md").read_text(encoding="utf-8")
        assert not read_json(imported / "course.json")["facts"]
        malformed_target.mkdir(); (malformed_target / "sentinel.txt").write_text("keep", encoding="utf-8")
        bad = work / "broken.synopsis"; bad.write_bytes(b"not a zip")
        try: import_course(bad, malformed_target / "new-course")
        except ImportErrorForSpike as e: assert str(e) == "invalid ZIP"
        else: raise AssertionError("malformed archive accepted")
        assert (malformed_target / "sentinel.txt").read_text(encoding="utf-8") == "keep"
        print("PASS: ZIP import/export; PDF/image bytes; card/note deletion; malformed rejection")
        print("EXPECTED ERROR: invalid ZIP (existing storage unchanged)")
        return 0
    finally:
        try:
            shutil.rmtree(work)
        except OSError as e:
            print("WARNING: could not clean transfer-spike work directory: " + str(e), file=sys.stderr)


if __name__ == "__main__": sys.exit(main())
