"""Regressions for the commands exposed by the rebuilt browser interface."""
import shutil
import hashlib
import io
import json
import zipfile
import unittest
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from server.application import SynopsisApplication
from storage import FileCourseStorage, StorageError
from synopsis_domain import DomainError, NoteId
from transfer import ArchiveError


class BrowserCommandTests(unittest.TestCase):
    def setUp(self):
        self.root=Path.cwd()/'.ui-test-data'/('api-'+uuid4().hex)
        self.root.mkdir(parents=True)
        self.addCleanup(lambda:shutil.rmtree(self.root))
        self.app=SynopsisApplication(FileCourseStorage(self.root))
        self.course=self.app.create_course('Линейная алгебра')
        self.cid=self.course.id

    def note(self,**kwargs):
        return self.app.create_note(self.cid,kind='concept',title='Вектор',**kwargs)

    def test_concurrent_saves_do_not_lose_notes_or_drafts(self):
        with ThreadPoolExecutor(max_workers=6) as pool:
            notes=list(pool.map(lambda i:self.app.create_note(self.cid,kind='concept',title=str(i)),range(20)))
        self.assertEqual(len(self.app.snapshot(self.cid).notes),20)
        n=notes[0]
        self.app.save_markdown(self.cid,n.id,'first',0)
        with self.assertRaises(DomainError): self.app.save_markdown(self.cid,n.id,'stale',0)
        self.assertEqual(self.app.snapshot(self.cid).notes[n.id].markdown,'first')

    def test_delete_lecture_keeps_children_and_clears_structural_references(self):
        lecture,box=self.app.create_lecture(self.cid,'Лекция 1')
        child=self.note(with_card=True,lecture_note_id=lecture.id)
        source=self.app.import_source(self.cid,'source.pdf',b'%PDF-1.4\n%%EOF',lecture.id)
        before=self.app.snapshot(self.cid)
        card=next(c for c in before.cards.values() if c.note_id==child.id)
        self.app.delete_note(self.cid,lecture.id)
        after=self.app.snapshot(self.cid)
        self.assertIn(child.id,after.notes)
        self.assertIsNone(after.notes[child.id].defined_in_lecture_note_id)
        self.assertIsNone(after.cards[card.id].lecture_box_id)
        self.assertEqual(after.cards[card.id].position,card.position)
        self.assertEqual(after.lecture_source_attachments,[])
        self.assertIn(source.id,after.sources)
        self.app.export_course(self.cid)

    def test_utf16_second_phrase_and_escapes_patch_only_exact_selection(self):
        target=self.note()
        raw='😀 повтор повтор и \\[скобки\\]'
        n=self.note(markdown=raw)
        request={'note_id':n.id,'revision':0,'raw_start':10,'raw_end':16,'selected_text':'повтор','target_note_id':target.id}
        self.app.selection_command(self.cid,'link',request)
        saved=self.app.snapshot(self.cid).notes[n.id]
        self.assertEqual(saved.markdown,f'😀 повтор [повтор](synopsis://note/{target.id}) и \\[скобки\\]')
        before=self.app.snapshot(self.cid)
        with self.assertRaises(DomainError): self.app.selection_command(self.cid,'create-note',{**request,'title':'stale'})
        self.assertEqual(self.app.snapshot(self.cid),before)

    def test_selection_new_note_fact_failure_and_missing_source(self):
        n=self.note(markdown='первый второй')
        data={'note_id':n.id,'revision':0,'raw_start':0,'raw_end':6,'selected_text':'первый','title':'Новый'}
        before=self.app.snapshot(self.cid)
        with patch.object(self.app.storage,'save',side_effect=StorageError('disk full')):
            with self.assertRaises(StorageError):self.app.selection_command(self.cid,'create-note',data)
        self.assertEqual(self.app.snapshot(self.cid),before)
        fact=self.app.selection_command(self.cid,'fact',{**data,'markdown':'Комментарий'})
        other=self.note(markdown='чужой')
        with self.assertRaises(ValueError):self.app.selection_command(self.cid,'attach-fact',{'note_id':other.id,'revision':0,'raw_start':0,'raw_end':5,'selected_text':'чужой','fact_id':fact.id})
        self.assertEqual(self.app.snapshot(self.cid).edges,{})

    def test_free_positions_and_source_copy_are_stable(self):
        a=self.note(with_card=True);b=self.note(with_card=True)
        s=self.app.snapshot(self.cid)
        positions=[c.position for c in s.cards.values()]
        self.assertNotEqual(positions[0],positions[1])
        card=self.app.create_card(self.cid,a.id)
        self.assertEqual(len(self.app.snapshot(self.cid).cards),2)
        source=self.app.import_source(self.cid,'Файл.pdf',b'%PDF-1.4\n%%EOF')
        self.assertIn('#page=2',self.app.source_open(self.cid,source.id,2).url)
        with self.assertRaises(ValueError): self.app.source_open(self.cid,source.id,0)
        with self.assertRaises(StorageError):self.app.snapshot('../outside')

    def test_untrusted_archive_asset_path_cannot_escape_staging(self):
        self.app.import_source(self.cid,'PDF.pdf',b'%PDF-1.4\n%%EOF')
        content=self.app.export_course(self.cid)
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            files={name:archive.read(name) for name in archive.namelist()}
        data=json.loads(files['course.json'])
        data['assets'][0]['relative_path']='../../../escaped.pdf'
        files['course.json']=json.dumps(data).encode()
        manifest=json.loads(files['manifest.json'])
        for item in manifest['files']:
            item['byteLength']=len(files[item['path']]);item['sha256']=hashlib.sha256(files[item['path']]).hexdigest()
        files['manifest.json']=json.dumps(manifest).encode()
        bad=io.BytesIO()
        with zipfile.ZipFile(bad,'w') as archive:
            for name,raw in files.items():archive.writestr(name,raw)
        before=self.app.list_courses()
        with self.assertRaises(ArchiveError):self.app.import_course(bad.getvalue())
        self.assertEqual(self.app.list_courses(),before)
        self.assertFalse((self.root/'escaped.pdf').exists())

    def test_reference_image_export_requires_local_asset(self):
        self.note(markdown='![рисунок][image]\n\n[image]: https://example.test/pic.png')
        with self.assertRaises(ArchiveError):self.app.export_course(self.cid)

    def test_lecture_and_selected_child_are_single_atomic_commands(self):
        before=self.app.snapshot(self.cid)
        with patch.object(self.app.storage,'save',side_effect=StorageError('disk full')):
            with self.assertRaises(StorageError):self.app.create_lecture(self.cid,'Lecture',summary='Summary',markdown='Body')
        self.assertEqual(self.app.snapshot(self.cid),before)
        lecture,box=self.app.create_lecture(self.cid,'Lecture',summary='Summary',markdown='Body')
        self.assertEqual(lecture.markdown,'Body')
        self.assertEqual(lecture.summary,'Summary')
        n=self.note(markdown='Базис пространства')
        child=self.app.selection_command(self.cid,'create-note',{'note_id':n.id,'revision':0,'raw_start':0,'raw_end':5,'selected_text':'Базис','title':'Базис','lecture_note_id':lecture.id})
        snap=self.app.snapshot(self.cid)
        self.assertEqual(child.defined_in_lecture_note_id,lecture.id)
        card=next(c for c in snap.cards.values() if c.note_id==child.id)
        self.assertEqual(card.lecture_box_id,box.id)
        self.assertGreater(card.position.x,box.position.x)
        self.assertGreater(card.position.y,box.position.y)
        self.assertEqual(snap.edges,{})


if __name__=='__main__':unittest.main()
