from concurrent.futures import ThreadPoolExecutor
import shutil
from pathlib import Path
import unittest
from uuid import uuid4

from storage import FileCourseStorage
from synopsis_mcp.workspace import AuthoringWorkspace, workspace_lock
from transfer import import_course


class AuthoringTests(unittest.TestCase):
    def setUp(self):
        self.root = Path.cwd() / '.ui-test-data' / ('mcp-' + uuid4().hex)
        self.workspace = AuthoringWorkspace(self.root)
        self.addCleanup(lambda: shutil.rmtree(self.root))
        self.cid = self.workspace.create_course('Линейная алгебра')['course_id']
        self.pid = self.workspace.register_presentation(self.cid, '01-vectors.pptx', 12)['presentation_id']
        self.cite = [{'presentation_id': self.pid, 'start_slide': 1, 'end_slide': 5}]

    def note(self, kind, title, lecture_id=None):
        return self.workspace.add_note(self.cid, kind, title, 'Определение: $v=(x,y)$.', self.cite, lecture_id)

    def unchanged(self, action):
        before = self.workspace.storage._course_path(self.cid).read_bytes()
        with self.assertRaises((ValueError, KeyError, RuntimeError)):
            action()
        self.assertEqual(before, self.workspace.storage._course_path(self.cid).read_bytes())

    def test_complete_course_round_trip(self):
        lecture = self.note('lecture', 'Лекция 1')
        second = self.note('lecture', 'Лекция 2')
        concept = self.note('concept', 'Вектор', lecture['id'])
        basis = self.note('concept', 'Базис', second['id'])
        for kind, edge_kind in [('example', 'exampleAttachment'), ('task', 'taskAttachment'), ('externalConcept', 'mention')]:
            n = self.note(kind, kind, lecture['id'])
            self.workspace.connect(self.cid, n['id'], concept['id'], edge_kind, 'Применяет определение')
        self.workspace.connect(self.cid, basis['id'], concept['id'], 'contextual', 'Состоит из векторов')
        fact = self.workspace.add_fact(self.cid, concept['id'], 'Пояснение из слайда.', self.cite)
        owner = self.workspace.get_note(self.cid, concept['id'])
        self.assertIn(fact['url'], owner['body'])
        self.workspace.update_note(self.cid, lecture['id'], f"См. [вектор]({concept['url']}).", lecture['revision'])
        result = self.workspace.export_course(self.cid)
        self.assertTrue(result['round_trip'])
        self.assertEqual((result['lectures'], result['cards'], result['edges']), (2, 5, 4))
        self.assertEqual(result['coverage_warnings'][0]['uncited_slides'], list(range(6, 13)))
        imported = import_course(FileCourseStorage(self.root / 'consumer'), Path(result['path']).read_bytes())
        self.assertEqual(imported.notes[concept['id']].defined_in_lecture_note_id, lecture['id'])
        for card in imported.cards.values():
            self.assertNotEqual(imported.notes[card.note_id].kind, 'lecture')
            if card.lecture_box_id:
                box = imported.lecture_boxes[card.lecture_box_id]
                self.assertGreaterEqual(card.position.x, box.position.x)
                self.assertGreaterEqual(card.position.y, box.position.y)
                self.assertLessEqual(card.position.x + card.size.x, box.position.x + box.size.x)
                self.assertLessEqual(card.position.y + card.size.y, box.position.y + box.size.y)
        self.assertEqual(self.workspace.export_course(self.cid)['path'], result['path'])

    def test_invalid_edges_and_foreign_ids_do_not_change_file(self):
        lecture = self.note('lecture', 'Лекция')
        concept = self.note('concept', 'Вектор', lecture['id'])
        example = self.note('example', 'Пример', lecture['id'])
        self.unchanged(lambda: self.workspace.connect(self.cid, example['id'], concept['id'], 'contextual', 'Неверно'))
        self.unchanged(lambda: self.workspace.connect(self.cid, lecture['id'], concept['id'], 'contextual', 'Неверно'))
        self.unchanged(lambda: self.workspace.connect(self.cid, concept['id'], concept['id'], 'contextual', 'Неверно'))
        other = self.workspace.create_course('Другой курс')['course_id']
        self.unchanged(lambda: self.workspace.add_note(self.cid, 'concept', 'Чужая лекция', '', self.cite, other))
        self.unchanged(lambda: self.workspace.add_fact(self.cid, 'missing', 'Текст', self.cite))

    def test_citations_duplicates_revision_and_links(self):
        lecture = self.note('lecture', 'Лекция')
        self.unchanged(lambda: self.note('lecture', 'Лекция'))
        self.unchanged(lambda: self.workspace.add_note(self.cid, 'concept', 'Без источника', '', []))
        self.unchanged(lambda: self.workspace.add_note(self.cid, 'concept', 'За пределами', '', [{'presentation_id': self.pid, 'start_slide': 13}]))
        self.unchanged(lambda: self.workspace.update_note(self.cid, lecture['id'], 'Текст', 20))
        self.unchanged(lambda: self.workspace.update_note(self.cid, lecture['id'], '[x](synopsis://note/missing)', 0))
        self.unchanged(lambda: self.workspace.update_note(self.cid, lecture['id'], '![x](file:///private.png)', 0))
        self.workspace.update_note(self.cid, lecture['id'], 'Новый конспект', 0)
        self.unchanged(lambda: self.workspace.update_note(self.cid, lecture['id'], 'Устаревший конспект', 0))

    def test_fact_is_scoped_to_owner(self):
        owner = self.note('lecture', 'Лекция')
        other = self.note('concept', 'Понятие')
        fact = self.workspace.add_fact(self.cid, owner['id'], 'Уточнение.', self.cite)
        self.unchanged(lambda: self.workspace.update_note(self.cid, other['id'], f"[x]({fact['url']})", 0))

    def test_attachment_boundaries_and_failed_signature(self):
        self.note('lecture', 'Лекция')
        self.unchanged(lambda: self.workspace.attach_file(self.cid, '../writer.lock'))
        bad = self.root / 'inputs' / 'not-an-image.png'
        bad.write_bytes(b'not a PNG')
        self.unchanged(lambda: self.workspace.attach_file(self.cid, str(bad)))
        with self.assertRaises(Exception):
            self.workspace.get_course('../outside')

    def test_concurrent_calls_do_not_lose_notes_and_frames_do_not_overlap(self):
        lectures = [self.note('lecture', f'Лекция {i}') for i in range(4)]
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda i: self.note('concept', f'Понятие {i}', lectures[i % 4]['id']), range(16)))
        self.assertEqual(len(self.workspace.get_course(self.cid)['notes']), 20)
        boxes = list(self.workspace.storage.load(self.cid).lecture_boxes.values())
        for i, a in enumerate(boxes):
            for b in boxes[i + 1:]:
                self.assertTrue(a.position.x + a.size.x <= b.position.x or b.position.x + b.size.x <= a.position.x
                                or a.position.y + a.size.y <= b.position.y or b.position.y + b.size.y <= a.position.y)

    def test_restart_recovers_drafts_and_lock_prevents_second_writer(self):
        self.note('lecture', 'Лекция')
        restarted = AuthoringWorkspace(self.root)
        self.assertEqual(len(restarted.get_course(self.cid)['notes']), 1)
        with workspace_lock(self.root):
            with self.assertRaises(OSError):
                with workspace_lock(self.root):
                    self.fail('Two writers acquired the same workspace')
        with workspace_lock(self.root):
            pass


if __name__ == '__main__':
    unittest.main()
