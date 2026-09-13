# Отчёт S06 — перенос .synopsis

## Состояние

- Этап: S06 — transfer/archive.
- Владелец: `/root/s06_transfer`.
- Статус: реализован и проверен на S01/S02 snapshot fixtures; реальная интеграция результатов S04/S05 пока недоступна в рабочем дереве.

## Результат

Добавлен `transfer/`: ZIP `.synopsis` schema v1 с `manifest.json`, `course.json`, Markdown всех Note/Fact и байтами assets. Метаданные карты (Card, LectureBox, Edge с geometry), appearance, course settings/styles/filters, Source и attachments сохраняются как часть course JSON.

Импорт сначала читает и полностью валидирует ZIP в памяти, затем создаёт новый `courseId` (D-04), сохраняет внутренние ID и публикует только валидную копию из UUID staging-каталога. Отказ до публикации не меняет существующие courses; неуспешная публикация убирает только собственный UUID asset staging target.

Валидаторы отклоняют ZIP corruption, unsafe/duplicate paths, лимиты entries/entry/total bytes, manifest/checksum mismatch, unsupported schema, duplicate IDs, чужой courseId, missing markdown/assets/references и invalid Edge endpoint/type. Dangling textual `synopsis://` URLs не анализируются как структура и поэтому допустимы. Markdown external image HTTP(S), `file:`, absolute Unix/Windows path выдаёт `externalDependency` и export отказывает: D-13 не позволяет назвать такой архив самодостаточным.

## Проверки

```powershell
python -m unittest -v tests/test_transfer.py tests/test_contracts.py tests/test_foundation.py
# Ran 16 tests ... OK

python -m unittest -v tests/test_transfer.py map.tests.test_map tests/test_s05_links_facts_sources.py
# Ran 19 tests ... OK

git diff --check
# no diff errors (Git printed only pre-existing CRLF warnings for S02 docs)
```

`tests/test_transfer.py` проверяет чистое storage export/import, exact PNG/PDF bytes, Note без Card, Fact без маркера, Edge control point и styles/filters; repeat import/new course IDs при тех же internal IDs; malformed/unsafe/corrupt ZIP без изменения sentinel course; unsupported schema, duplicate ZIP entry и oversize limit; D-13 external image diagnostic.

## Ограничения и передача

S04/S05 появились в дереве в ходе S06; их 9 map и 5 links/facts/sources tests выполнены в одной команде с transfer tests, без изменения их модулей. Это подтверждает совместимость общего `CourseSnapshot`, включая `Course.settings` и `Edge.geometry`, но не является browser-level export/import UI приёмкой. Контракт использует текущий S02 `FileCourseStorage`; интегратор должен добавить export/import UI и повторить acceptance fixture с browser host. Многопроцессная координация storage остаётся ограничением S02.
