# S08 — независимая release-приёмка

> Исторический отчёт о прежней сборке. После пользовательских замечаний UI
> переработан; текущие результаты браузерных проверок находятся в
> [UI-recovery-report.md](UI-recovery-report.md). Этот отчёт сохранён без
> ретроспективного изменения release gate.

Дата: 2026-09-13. Проверяющий: `/root/s08_release_qa` (не автор основной реализации).

## Итог

**Release gate: BLOCKED / не принят.** Обязательные AC-01–31 не имеют полного
воспроизводимого доказательства; часть обязательных пользовательских путей
фактически отсутствует в текущем localhost UI. AC-32 не проверялся, он
неблокирующий.

## Реально воспроизведённые проверки

Среда: Windows, PowerShell, CPython 3.14, `127.0.0.1`. Чистое хранилище:
`C:\Users\Bulkin\synopsis\_s08_clean_3b9c323fe71745baac5290caf9e17049`.

```powershell
python -m unittest -v tests/test_contracts.py tests/test_foundation.py tests/test_editor.py map.tests.test_map tests/test_s05_links_facts_sources.py tests/test_transfer.py tests/test_s07_http.py
# Ran 34 tests in 0.493s — OK

python -m server.http_server --data-dir C:\Users\Bulkin\synopsis\_s08_clean_3b9c323fe71745baac5290caf9e17049 --port 18473
Invoke-WebRequest http://127.0.0.1:18473/api/courses
# []
```

В отдельном чистом data-dir через публичные HTTP routes созданы два одноимённых
курса и по Note в каждом; сохранение первого повысило revision до `1`, а
повторное сохранение с revision `0` вернуло HTTP 400. Список курсов содержал
ровно два курса. Это подтверждает запуск, базовую запись и stale-revision
error path, но не заменяет browser E2E.

Требуемый browser visual QA не выполнен по внешнему блокеру: Computer Use
инвентаризация вернула `browsers: []`; открытие `iab` на
`http://127.0.0.1:18473/` вернуло `Browser is not available: iab`. Поэтому
никакой UI путь не отмечен выполненным только по исходнику или HTTP-моку.

## Матрица AC

| AC | Статус | Доказательство / причина |
| --- | --- | --- |
| 01 | Частично | Чистый server и `/api/courses` отвечают; визуально главная не проверена. |
| 02 | Частично | domain/S07 tests и изолированные courses; UI поиск не E2E. |
| 03 | Частично | map model/tests; визуальная рамка/преамбула не проверена. |
| 04 | Не выполнено | UI `New note` всегда отправляет `kind:'concept'`; нет UI создания external/example/task. |
| 05 | Не выполнено | HTTP command есть, но UI не создаёт edge; пересечение рамок не проверено. |
| 06 | Частично | map tests подтверждают matrix/cycle; public UI отсутствует. |
| 07 | Частично | domain/map tests; public UI отсутствует. |
| 08 | Не выполнено | UI рисует только прямой `<line>` и не имеет control-point UI; import/restart geometry не E2E. |
| 09 | Частично | S05/S07 tests подтверждают data path, UI отсутствует. |
| 10 | Не выполнено | Нет UI filter/type visibility; browser whole-map path не проверен. |
| 11 | Не выполнено | settings/styles нет в UI; visual card assertion не выполнена. |
| 12 | Частично | model tests; browser visual свободного размещения не проверен. |
| 13 | Частично | public Remove frame и domain/S07 tests, но visual world-coordinate assertion не выполнен. |
| 14 | Не выполнено | CSS grid фиксирован `55% 45%`, resize control отсутствует; tabs не E2E. |
| 15 | Не выполнено | raw save test есть, но read view сам экранирует Markdown вместо renderer. |
| 16 | Не выполнено | См. DEF-S08-01. |
| 17 | Не выполнено | Read view показывает только informative text; selection actions отсутствуют. |
| 18 | Частично | bounded HTTP/domain test есть; DOM selection/browser path отсутствует. |
| 19 | Частично | atomic command test есть; UI create-from-selection отсутствует. |
| 20 | Не выполнено | UI facts не показывает/не редактирует. |
| 21 | Частично | facts module tests; UI lifecycle отсутствует. |
| 22 | Не выполнено | source/PDF attach/open controls отсутствуют в UI; external intent не E2E. |
| 23 | Частично | module tests validate missing/page; UI diagnosis отсутствует. |
| 24 | Частично | Remove/Show card представлены, domain/S07 test; browser flow не проверен. |
| 25 | Частично | domain/S07 tests; invalid link read state не renderer/UI. |
| 26 | Частично | ID semantics module tests; rename/PDF UI path отсутствует. |
| 27 | Частично | persistence/write-failure tests и isolated stale save; browser draft recovery не проверен. |
| 28 | Частично | transfer tests cover clean storage/assets; export/import browser UI не проверен. |
| 29 | Выполнено на HTTP/data уровне | transfer and S07 tests reject corrupt/unsupported archives without publication. |
| 30 | Выполнено на data уровне | transfer test verifies repeat import/new course ID and isolation. |
| 31 | Выполнено по inspection/tests | No AI, auto structural import, sections, questions, collaboration, or collapse found. |
| 32 | Не проверялось | Optional. |

## Дефекты для владельца интеграции

### DEF-S08-01 — Markdown reader не использует безопасный renderer

Серьёзность: **blocker** (AC-15, AC-16, FR-042–046, FR-051).

Шаги:

1. Создать Note и сохранить Markdown с таблицей, `![image](synopsis://asset/...)`, `$x$`, `$$...$$`, matrix/cases.
2. Открыть Note и выбрать `Read`.

Ожидание: formatted Markdown, локальное изображение и inline/block formula;
ошибка formula локальна, raw сохраняется.

Факт: `shell/page.py`, функция `read()`, делает только HTML escape + newline to
`<br>` and one internal-note regex. Markdown delimiters/tables/formulas/images
are shown as literal text; `render.render_markdown` is never called by the
page. Browser visual proof additionally blocked by unavailable browser.

### DEF-S08-02 — обязательные browser UI actions карты отсутствуют

Серьёзность: **blocker** (AC-04–08, AC-10–12).

Шаги: открыть курс; попытаться создать external concept/example/task, создать
edge, изменить type filter/style, label или control point.

Ожидание: все действия доступны в UI и сохраняются.

Факт: UI has only `New note` with `kind:'concept'`, `New lecture`, card drag,
remove/show card and remove frame. `renderMap()` emits straight SVG `<line>`;
there are no controls for edge creation/labels/control points/filter/settings.

### DEF-S08-03 — selection/fact/source-PDF пользовательские пути отсутствуют

Серьёзность: **blocker** (AC-17–23).

Шаги: в Read выделить обычный текст; попытаться создать link/new Note/fact/PDF
source/page link, reveal/edit Fact, attach/open PDF.

Ожидание: permitted bounded selection actions, fact lifecycle and an external
new-tab PDF intent with diagnostics.

Факт: `read()` only prints an informational sentence about HTTP API; no action
controls. The shell has no source attach/open or fact UI. The public adapter
modules and routes do not constitute the required user path.

### DEF-S08-04 — две области не изменяют размер

Серьёзность: **major** (AC-14, FR-040).

Шаги: открыть курс and look for pane resize affordance.

Ожидание: map and note panel dimensions can be changed.

Факт: `.work` is fixed CSS `grid-template-columns:55% 45%`; no splitter or
resize handler is implemented.

## Размер, offline и platform scope

ADR-001 measurement fixture (20 lectures / 250 cards / 500 edges / 250 MiB)
не создана и не измерена. Offline/no-external-request browser capture was not
possible because no browser surface was available. Do not state a supported
browser/OS performance baseline or offline guarantee for this release.

## Required next gate

Implement and expose the missing UI paths, then rerun the AC matrix on an
available Chrome or Edge surface using a clean data-dir and a complete control
course; specifically inspect Markdown/formulas/assets, SVG geometry/filter,
selection/facts/PDF external intent, deletion/restoration, archive repeat
import and network requests. Re-run performance and offline checks only with
measured results.
