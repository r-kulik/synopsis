# Отчёт S03 — Markdown-редактор и чтение

## Состояние

- Этап: S03.
- Владелец: `/root/s03_editor`.
- Статус: модульная часть готова; подключение browser UI требует короткой интеграции владельцем `shell/` и `server/`.
- Область изменений: только `editor/`, `render/`, `markdown/`, S03 fixtures/tests и этот отчёт.

## Результат

`editor.DraftTabs` хранит только черновик открытой вкладки (`text`, базовую
revision, dirty/error). Сохранённый Markdown гидратируется вызывающим кодом из
S02 snapshot и сохраняется только вызовом
`SynopsisApplication.save_markdown(course_id, note_id, markdown, revision)`.
Неизменённый source не сериализуется в rich-text/AST и при read→edit остаётся
той же строкой. Переключение/повторное открытие вкладки не выбрасывает dirty
draft; закрытие возвращает состояние `confirm`; ошибка save оставляет его в
памяти с диагностикой.

`render.render_markdown(raw, snapshot)` — dependency-free безопасное чтение
профиля v1: заголовки, абзацы, списки, строковое представление GFM-таблиц,
обычные ссылки, internal links, local asset images и `$`/`$$` formula display.
Он не исполняет raw HTML. Формулы показаны как локально стилизуемый текст, а
не как полноценный TeX layout engine: поддержка матриц/cases в этом baseline
видима в исходнике, но не является обещанием KaTeX/MathJax-типографики.

Internal URL разбирается только общим `synopsis_domain.parse_internal_url`,
существование проверяет `CourseService.resolve_internal_url`. Неизвестные,
удалённые или malformed targets остаются читаемыми `invalid-link`; сохранение
не блокируется. Asset ID получает course-scoped URL S02. Remote HTTP(S)
images получают `remoteImage`, local file paths — `localImagePath`: они не
загружаются и не выдаются за переносимые вложения (D-13). Небезопасные
formula commands имеют `invalidFormula`, исходник остаётся видимым.

## API для S05

`RenderedMarkdown` возвращает `html`, `diagnostics` и immutable `spans`.
Каждый `SourceSpan(raw_start, raw_end, rendered_text, selectable=True)` —
точный Python-Unicode offset в исходной строке только для обычной inline text
строки, свободной от ссылок, image, code и math syntax. S05 может создавать
raw patch только когда browser Range целиком сопоставлен одному такому span и
revision ещё актуальна. Formulae, images, code, Markdown delimiters и
cross-line/cross-span selection намеренно не mapped: UI обязан отказать без
изменения Markdown. Это не ложное обещание полного DOM mapping; browser UTF-16
offset adaptation и атомарная command `create_note_from_selection` остаются
работой S05.

## Проверки

```powershell
python -m unittest -v tests/test_editor.py
# Ran 3 tests ... OK

python -m unittest -v tests/test_contracts.py tests/test_foundation.py
# Ran 11 tests ... OK

python experiments/markdown/spike.py
# PASS 11/11: source-mapped selection patches and refusals verified

git diff --check
# no errors
```

`tests/test_editor.py` покрывает Unicode round-trip и switching dirty draft,
asset-ID image, remote/local-path diagnostics, dangling internal URL,
malformed formula и явную ограниченность source-map. Fixture
`tests/fixtures/s03_markdown_cases.md` содержит таблицу, matrix, Unicode и
невалидную формулу.

Локальный HTTP smoke:

```powershell
python -m server.http_server --data-dir .synopsis-data-s03-smoke --port 8765
Invoke-WebRequest http://127.0.0.1:8765/
# HTTP 200; S02 editor host visible
```

## Ограничения и передача

S02 server сейчас не отдаёт модули S03 и не имеет HTTP save endpoint; его
`shell/page.py` содержит только placeholder. По правилам владения S03 не
изменял `shell/` или `server/`, поэтому реальная browser edit/save/read visual
inspection, tabs UI и AC-14–16/27 как end-to-end нельзя честно объявить
выполненными до интеграции. Интегратор должен добавить route/static delivery,
adapter с обязательным S02 `save_markdown` и tab host, после чего повторить
browser visual cases: long text, table, matrix/cases, asset image, Unicode,
invalid formula/link и draft tab switch.

Не добавлены WYSIWYG, AI, MathLive, PDF-viewer, selection/fact UI, карта или
автоматическое создание сущностей из Markdown.
