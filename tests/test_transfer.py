import io
import json
import unittest
import zipfile
from pathlib import Path

from storage import FileCourseStorage
from synopsis_domain.model import *
from transfer import ArchiveError, ArchiveLimits, export_course, import_course


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.root = Path.cwd() / "_storage_smoke" / "s06"
        self.root.mkdir(parents=True, exist_ok=True)
        self.storage = FileCourseStorage(self.root)

    def fixture(self, course_id="course-a"):
        c = Course(CourseId(course_id), "Linear algebra", settings={"styles":{"concept":{"color":"blue"}}, "filters":{"fact":False}})
        lecture=Note(NoteId("lecture"),c.id,NoteKind.LECTURE,"Vectors","intro","# Vectors")
        concept=Note(NoteId("vector"),c.id,NoteKind.CONCEPT,"Vector","array","![plot](synopsis://asset/img)",defined_in_lecture_note_id=lecture.id)
        orphan=Note(NoteId("orphan"),c.id,NoteKind.CONCEPT,"Cardless","kept","outside card")
        ext=Note(NoteId("external"),c.id,NoteKind.EXTERNAL_CONCEPT,"Cosine","","text")
        cards={CardId("c-vector"):Card(CardId("c-vector"),c.id,concept.id,Point(10,20),appearance={"shape":"round"}), CardId("c-ext"):Card(CardId("c-ext"),c.id,ext.id,Point(80,40))}
        box=LectureBox(LectureBoxId("box"),c.id,lecture.id,Point(0,0),Point(300,200))
        edge=Edge(EdgeId("edge"),c.id,EdgeKind.MENTION,CardId("c-ext"),CardId("c-vector"),"uses",EdgeGeometry([RelativeControlPoint(.2,.3)]))
        fact=Fact(FactId("fact"),c.id,orphan.id,"unanchored fact")
        asset=Asset(AssetId("img"),c.id,"image/png","img","plot.png",b:=len(b"PNG\x00bytes"),None)
        pdf=Asset(AssetId("pdf"),c.id,"application/pdf","pdf","lecture.pdf",len(b"%PDF bytes"),None)
        source=Source(SourceId("source"),c.id,"slides",pdf.id,3)
        snap=CourseSnapshot(c,{x.id:x for x in (lecture,concept,orphan,ext)},cards,{box.id:box},{edge.id:edge},{fact.id:fact},{source.id:source},{asset.id:asset,pdf.id:pdf},[LectureSourceAttachment(lecture.id,source.id,1)])
        self.storage.save(snap)
        # Files are deliberately independent from the source paths named in metadata.
        for a, data in ((asset,b"PNG\x00bytes"),(pdf,b"%PDF bytes")):
            folder=self.storage.assets / str(c.id); folder.mkdir(exist_ok=True); (folder / a.relative_path).write_bytes(data)
        return snap

    def test_round_trip_clean_storage_bytes_cardless_fact_geometry_and_styles(self):
        original=self.fixture(); archive=export_course(self.storage, original.course.id).content
        clean=FileCourseStorage(self.root / "clean")
        loaded=import_course(clean,archive)
        self.assertNotEqual(loaded.course.id, original.course.id)
        self.assertEqual(loaded.notes[NoteId("orphan")].markdown,"outside card")
        self.assertEqual(loaded.facts[FactId("fact")].markdown,"unanchored fact")
        self.assertEqual(loaded.edges[EdgeId("edge")].geometry.control_points[0],RelativeControlPoint(.2,.3))
        self.assertEqual(loaded.course.settings["styles"]["concept"]["color"],"blue")
        self.assertEqual(clean.get_asset(loaded.course.id,"img")[1],b"PNG\x00bytes")
        self.assertEqual(clean.get_asset(loaded.course.id,"pdf")[1],b"%PDF bytes")

    def test_repeated_import_and_matching_internal_ids_are_isolated(self):
        snap=self.fixture(); blob=export_course(self.storage,snap.course.id).content
        target=FileCourseStorage(self.root / "copies")
        first=import_course(target,blob); second=import_course(target,blob)
        self.assertNotEqual(first.course.id,second.course.id)
        self.assertEqual(first.notes[NoteId("vector")].id,second.notes[NoteId("vector")].id)
        self.assertEqual(target.get_asset(first.course.id,"img")[1],target.get_asset(second.course.id,"img")[1])

    def test_invalid_archives_do_not_change_existing_storage(self):
        sentinel=self.fixture("sentinel"); before=self.storage._course_path("sentinel").read_bytes()
        for blob in (b"broken", self._mutate(lambda z: z.writestr("../evil",b"x")), self._mutate(lambda z: z.writestr("course.json",b"{}"))):
            with self.assertRaises(ArchiveError): import_course(self.storage,blob)
            self.assertEqual(self.storage._course_path("sentinel").read_bytes(),before)

    def test_unsupported_duplicate_and_oversized_archives_rejected(self):
        snap=self.fixture(); blob=export_course(self.storage,snap.course.id).content
        bad=self._rewrite(blob, lambda files: files.__setitem__("manifest.json", json.dumps({**json.loads(files["manifest.json"]),"schemaVersion":99}).encode()))
        with self.assertRaises(ArchiveError) as cm: import_course(self.storage,bad)
        self.assertEqual(cm.exception.diagnostic.code,"unsupportedSchemaVersion")
        dup=self._mutate(lambda z: z.writestr("notes/vector.md",b"duplicate"))
        with self.assertRaises(ArchiveError): import_course(self.storage,dup)
        with self.assertRaises(ArchiveError): import_course(self.storage,blob,limits=ArchiveLimits(max_total_bytes=10))

    def test_external_image_is_diagnostic_and_not_claimed_self_contained(self):
        snap=self.fixture(); snap.notes[NoteId("vector")].markdown="![remote](https://example.test/x.png)"
        self.storage.save(snap)
        with self.assertRaises(ArchiveError) as cm: export_course(self.storage,snap.course.id)
        self.assertEqual(cm.exception.diagnostic.code,"externalDependency")

    def _mutate(self, change):
        out=io.BytesIO()
        with zipfile.ZipFile(out,"w") as z: change(z)
        return out.getvalue()
    def _rewrite(self, blob, change):
        with zipfile.ZipFile(io.BytesIO(blob)) as z: files={n:z.read(n) for n in z.namelist()}
        change(files); out=io.BytesIO()
        with zipfile.ZipFile(out,"w") as z:
            for n,b in files.items(): z.writestr(n,b)
        return out.getvalue()

if __name__ == "__main__": unittest.main()
