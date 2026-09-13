# ADR-001 — технический baseline после S00

Дата: 2026-09-13. Статус: принято для S01; конкретные production-версии закрепляются в lockfile при создании приложения.

## Контекст

Нужно снять риски AC-08, AC-18 и AC-28 до создания общего приложения. Репозиторий на S00 не содержит Node.js, frontend-пакетов или production-модулей; прототипы поэтому проверяют данные и операции на Python 3.14 standard library, а не заменяют последующую browser-интеграцию.

## Решения

### D-01, D-14: архитектура, запуск и offline

- Production baseline: TypeScript + React UI, CodeMirror 6 для raw Markdown, unified/remark/rehype для AST и безопасного чтения, KaTeX для оговорённого математического профиля, `@xyflow/react` для canvas-карты и `fflate` для ZIP. Сервер — один локальный TypeScript-процесс на loopback; storage candidate — SQLite для метаданных и каталог assets по ID.
- Не использовать CDN; ресурсы и шрифты пакуются локально. Не добавлять облако, графовую БД, PDF viewer, WYSIWYG, AI, sections или collapse.
- Проверенная среда S00: Windows, PowerShell, CPython 3.14; Node.js отсутствовал. Цель первого browser gate: Windows 11, текущие Chrome и Edge (Chromium). Firefox/macOS/Linux не заявлены до S08-проверки.
- Предварительно выбранные кандидаты и лицензии на дату ADR: `@xyflow/react` 12.11.2 — MIT; `@codemirror/view` 6.43.11 — MIT; unified/remark/rehype и fflate — MIT по официальным проектам. Точные совместимые версии, транзитивные лицензии и команды установки — обязанность единственного владельца manifest/lockfile на S01/S02.

### D-02, D-03: Markdown и selection

- Поддерживаемый профиль остаётся: CommonMark + GFM tables/strikethrough/task lists и `$…$`/`$$…$$` с проверочным набором KaTeX из `markdown-contract.md`. Raw HTML не исполняется.
- Команда selection работает только по source-mapped, не пустому диапазону в одной поддерживаемой текстовой области и с ожидаемой revision. Патч меняет один известный raw range; остальной Markdown не пересериализуется.
- S00 доказал: повтор фразы, кириллицу/emoji, часть strong, escapes, ячейку таблицы и текст рядом с inline-формулой. На S01/S03 намеренно отказать без изменения документа для существующей ссылки, inline/display math, inline/fenced code, пустого/неотображённого диапазона, границы блоков или устаревшей revision. Многострочные и пересекающие runs selection, изображения, raw HTML, task lists и DOM UTF-16 mapping ещё не доказаны и не должны молча приниматься.
- Выбранный production-кандидат — remark/rehype с собственным range-mapping layer; markdown-it отклонён для этой задачи, потому что его token map покрывает строки, а не точные source offsets. Browser spike обязан отдельно проверить DOM Range и UTF-16 offsets.

### D-10: карта и ручная геометрия

- Сохранять control points и label в Edge.geometry. Для полилинии контрольная точка хранится endpoint-relative: `P = S + u(T-S) + v*perpendicular(T-S)`. Перемещение карточки обновляет endpoint; перемещение рамки сдвигает саму рамку и дочерние карточки в мировых координатах.
- Фильтр типа не меняет данные; скрывается ребро, если скрыт любой его конец. Hierarchy между concept допускает циклы; остальные типы валидируются матрицей.
- React Flow Editable Edge не использовать и не копировать: это пример по xyflow Pro License. React Flow MIT используется только как кандидат canvas/drag/SVG infrastructure; UI control-points пишутся независимо и проверяются в browser spike.

### D-11: контрольный размер

- Базовая fixture — контрольный курс «Линейная алгебра» из acceptance: 2 лекции, заданные Note/Card/Fact/asset и межлекционное ребро с двумя точками.
- Для S08 добавить measurement fixture: 20 лекций, до 250 Note/Card, до 500 Edge и до 250 MiB локальных assets. Это объём проверки, не обещание численного SLA до измерения на объявленной платформе.

### Архив

- `.synopsis` — ZIP с `manifest.json`, `course.json`, `notes/`, `facts/`, `assets/`; manifest содержит schemaVersion, размер и SHA-256 каждого файла.
- Импорт сначала проверяет ZIP, безопасные и уникальные пути, manifest/checksums и связи, затем публикует staging snapshot. Невалидная текстовая Note-ссылка допускается как текст; структурная ошибка отклоняет импорт без изменения существующего хранения.

## Доказательства

- `experiments/markdown/spike.py`: 11/11 source-mapped patch/refusal cases.
- `experiments/map/map_spike.py`: 4/4 data/geometry cases, включая JSON reload.
- `experiments/transfer/transfer_spike.py`: ZIP export/import, фактические PDF/PNG bytes, Note без Card и reject malformed ZIP.

## Последствия

S01 обязан закрепить публичные типы, URL parser/generator, expectedRevision и атомарную command boundary. S03/S04 обязаны повторить риски в реальном браузере: эти Python spikes не доказывают production UI, parser conformance, pointer interaction или persistence implementation.
