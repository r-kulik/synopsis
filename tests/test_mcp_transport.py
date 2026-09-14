"""Run with the optional .venv-mcp interpreter to test the actual stdio protocol."""
import importlib.util
import os
from pathlib import Path
import shutil
import sys
import subprocess
import unittest
from uuid import uuid4


@unittest.skipUnless(importlib.util.find_spec('mcp') and importlib.util.find_spec('pypdf'), 'Optional MCP environment required')
class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_official_client_typed_tools_failures_pdf_and_export(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        from pypdf import PdfWriter
        from storage import FileCourseStorage
        from transfer import import_course

        root = Path.cwd() / '.ui-test-data' / ('mcp-stdio-' + uuid4().hex)
        inputs = root / 'inputs'
        inputs.mkdir(parents=True)
        self.addCleanup(lambda: shutil.rmtree(root))
        pdf = PdfWriter()
        pdf.add_blank_page(width=640, height=480)
        pdf.add_blank_page(width=640, height=480)
        pdf.write(inputs / 'slides.pdf')
        params = StdioServerParameters(command=sys.executable, args=[str(Path.cwd() / 'tools/run-mcp.py'), '--workspace', str(root)])
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                tools = (await session.list_tools()).tools
                self.assertIn('add_fact', {t.name for t in tools})
                connect_schema = next(t.inputSchema for t in tools if t.name == 'connect')
                self.assertIn('exampleAttachment', connect_schema['properties']['kind']['enum'])

                async def call(name, **args):
                    result = await session.call_tool(name, args)
                    self.assertFalse(result.isError, result.content)
                    return result.structuredContent

                cid = (await call('create_course', title='Тест MCP'))['course_id']
                pid = (await call('register_presentation', course_id=cid, filename='slides.pdf', slide_count=2))['presentation_id']
                citations = [{'presentation_id': pid, 'start_slide': 1, 'end_slide': 2}]
                lecture = await call('create_lecture', course_id=cid, title='Лекция 1', markdown='Введение.', citations=citations)
                concept = await call('add_concept', course_id=cid, title='Вектор', markdown='$v=(x,y)$', citations=citations, lecture_id=lecture['id'])
                example = await call('add_example', course_id=cid, title='Вектор на плоскости', markdown='$(1,2)$', citations=citations, lecture_id=lecture['id'])
                bad = await session.call_tool('connect', dict(course_id=cid, source_note_id=example['id'], target_note_id=concept['id'], kind='contextual', label='Недопустимо'))
                self.assertTrue(bad.isError)
                self.assertEqual(len((await call('get_course', course_id=cid))['edges']), 0)
                bad = await session.call_tool('add_task', dict(course_id=cid, title='Плохая ссылка', markdown='', citations=[{'presentation_id': pid, 'start_slide': '1'}]))
                self.assertTrue(bad.isError)
                await call('connect', course_id=cid, source_note_id=example['id'], target_note_id=concept['id'], kind='exampleAttachment', label='Пример координат')
                await call('add_fact', course_id=cid, owner_note_id=concept['id'], markdown='Координаты зависят от базиса.', citations=citations)
                attached = await call('attach_file', course_id=cid, path='slides.pdf', lecture_id=lecture['id'])
                self.assertEqual(attached['page_count'], 2)
                bad = await session.call_tool('update_note', dict(course_id=cid, note_id=lecture['id'], markdown=f"[Страница]({attached['url']}?page=3)", expected_revision=0))
                self.assertTrue(bad.isError)
                await call('update_note', course_id=cid, note_id=lecture['id'], markdown=f"[Страница]({attached['url']}?page=2)", expected_revision=0)
                exported = await call('export_course', course_id=cid)
                self.assertTrue(exported['round_trip'])
                imported = import_course(FileCourseStorage(root / 'consumer'), Path(exported['path']).read_bytes())
                self.assertEqual(len(imported.sources), 1)
                self.assertEqual(len(imported.facts), 1)
                self.assertEqual(len(imported.edges), 1)
                self.assertEqual(imported.notes[example['id']].defined_in_lecture_note_id, None)
                if os.environ.get('SYNOPSIS_MCP_BROWSER_TEST') == '1':
                    node = shutil.which('node') or str(Path.cwd() / '.tools/node-v22.23.2-win-x64/node.exe')
                    subprocess.run([node, 'tests/ui/mcp-preview.mjs', sys.executable, str(root / 'consumer'),
                                    str(imported.course.id), concept['id']], check=True, timeout=45)


if __name__ == '__main__':
    unittest.main()
