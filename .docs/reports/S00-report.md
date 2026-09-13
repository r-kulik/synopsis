# Отчёт S00 — проверка рисков и технических кандидатов

## Состояние

- Этап: S00 — проверка рисков и технических кандидатов.
- Исполнители: интегратор `/root`; ограниченные владельцы `experiments/markdown`, `experiments/map`, `experiments/transfer`.
- Статус: принят в границах spike; production browser-интеграция остаётся работой S01–S06.
- База проверки: начальный commit `918ad7f`; новые незафиксированные S00-файлы в `experiments/` и `.docs/adr/001-s00-technical-baseline.md`.

## Результат

Созданы три автономных, воспроизводимых Python-прототипа без изменения общих manifest/lockfile/API. ADR-001 фиксирует стек-кандидаты, лицензии, профиль Markdown, правило геометрии, архив и платформу. Никакой прототип не объявлен production-модулем.

## Прослеживаемость

| FR / AC | Статус | Доказательство или воспроизведение |
| --- | --- | --- |
| FR-047, FR-048, FR-051 / AC-17, AC-18 | Выполнено в границах spike | `python experiments/markdown/spike.py`: 11/11; точечный patch второй одинаковой фразы, Unicode, emphasis, escapes, table cell, formula adjacency; unsafe contexts/revision отказаны без patch. |
| FR-020, FR-026, FR-034 / AC-08 | Выполнено в границах spike | `python experiments/map/map_spike.py`: 4/4; two lecture boxes, labelled cross-lecture edge, points, endpoint/container movement, JSON restore, cycle and filter. |
| FR-005, FR-081–084 / AC-28 | Выполнено в границах spike | `python experiments/transfer/transfer_spike.py`: actual ZIP plus PDF/PNG byte equality after clean import; cardless Note/Fact; malformed ZIP rejection preserves sentinel. |
| AC-08, AC-18, AC-28 as product/browser acceptance | Не выполнено | Проверены только data-operation spikes; real React/DOM/persistence/export UI обязаны пройти S03–S08. |

## Проверки

Среда: Windows, PowerShell, CPython 3.14.0. Node.js отсутствует; поэтому production npm dependencies не устанавливались и lockfile не создан.

```powershell
python experiments/markdown/spike.py
# PASS 11/11: source-mapped selection patches and refusals verified

python experiments/map/map_spike.py
# Ran 4 tests ... OK

python experiments/transfer/transfer_spike.py
# PASS: ZIP import/export; PDF/image bytes; card/note deletion; malformed rejection
# EXPECTED ERROR: invalid ZIP (existing storage unchanged)

git diff --check
# no output
```

Интегратор также воспроизвёл все три команды. Первичный вариант transfer-spike создавал временный каталог с правами, недоступными обычному запуску; дефект обнаружен при независимом запуске и исправлен уникальным рабочим каталогом внутри `experiments/transfer` до принятия S00.

## Решения и ограничения

Принят ADR-001: конкретизированы D-01, D-02, D-03, D-10, D-11 и D-14. Версии кандидатов не являются установленными зависимостями; их нужно повторно подтвердить при lockfile. Отдельный React Flow Editable Edge имеет xyflow Pro License и исключён. Точная DOM-to-source mapping, полный CommonMark/GFM, browser pointer controls, KaTeX coverage, SQLite/local server и UI import/export пока не доказаны.

## Передача следующему этапу

- S01 владеет первым общим контрактом и manifest/lockfile; пути production модулей ещё свободны.
- Использовать fixtures/spikes только как регрессионные данные и oracle поведения, не как production API.
- Зафиксировать parser/generator `synopsis://`, course scope, expectedRevision source patch, атомарный CreateNoteFromSelection, Edge.geometry, schemaVersion/import-copy policy и import limits.
- S03 обязан провести browser-level Markdown/source-map spike; S04 — custom SVG control-point interaction без Pro code; S06 — production ZIP/staging with limits and diagnostics.

## Проверка интегратором

Дата: 2026-09-13. Проверены все три исполняемые команды и `git diff --check`; transfer повторно проверен после исправления прав временной папки. Итог gate S00: принят только как feasibility evidence; нет оснований считать AC выполненными для финального продукта до следующих этапов.
