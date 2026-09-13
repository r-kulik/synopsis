# ADR-002 — доменные контракты S01

Дата: 2026-09-13. Статус: принято для S02–S06. Связанные решения: D-04–D-09, D-12, D-15.

## Контекст

После S00 нужны независимые от React, Markdown-рендера и конкретного хранилища правила, чтобы карта, редактор и перенос не расходились в идентичности объектов, удалении и атомарности операций.

## Решения

- Все публичные ID устойчивы только в пределах `courseId`; хранилище и API всегда получают контекст курса. `schemaVersion = 1`; архив экспортирует сохранённый `CourseSnapshot` и версии Note, но не черновики редактора (D-05).
- Повторный импорт создаёт независимую копию с новым `courseId`; внутренние ID сохраняются, так как их область действия — новый курс (D-04). Никакой импорт не перезаписывает курс неявно.
- Note бывает `lecture`, `concept`, `externalConcept`, `example`, `task`; Card имеет отношение 0..1 к Note. `definedInLectureNoteId` хранит семантическую лекцию определения только у обычного понятия. `lectureBoxId` — только визуальное членство (D-06, D-07, D-15).
- Новые внешние понятия, примеры и задачи могут быть свободными. Обычное понятие получает лекцию определения только по явной команде; карточка не обязана быть в рамке.
- Hierarchical направлено «общее → частное», допускает циклы из нескольких Card, но не self-loop. Contextual направлено от выбранного source к target, может иметь подпись; `mention`, `exampleAttachment`, `taskAttachment` направлены соответственно external/example/task → concept. Параллельные рёбра разных или одинаковых типов допустимы при разных ID (D-08).
- CourseRoot существует в представлении карты и получает title из Course, но не является Edge-узлом. Source и Fact также не являются картовыми узлами; у лекции минимум один необязательный PDF Source attachment. Замена источника создаёт/выбирает другой Source, а не меняет байты существующего, чтобы не исказить page-ссылки (D-09, D-12).
- Снятие Card удаляет только инцидентные Edge. Снятие LectureBox очищает `lectureBoxId`, сохраняя уже мировые позиции Card, лекционный Note и Edge. Удаление lecture Note удаляет лишь его Box/Fact/Card; оставшиеся Notes, Cards и связи не каскадируются. Удаление Note не переписывает Markdown других Note.
- `synopsis://{note|source|fact|asset}/{id}` разбирается одним parser/generator. Только Source допускает `?page=<positive integer>`. Нераспознанный или отсутствующий адрес — диагностика чтения, не ошибка сохранения Markdown.
- `SaveMarkdown` и `ApplySourcePatch` требуют `expectedRevision`; patch заменяет только предоставленный raw range, не пересериализуя документ. `CreateNoteFromSelection` в одной атомарной границе проверяет revision/range и создаёт Note, Card и raw patch; исключение откатывает всё. Fact имеет ровно одного владельца, а потерявший ссылку остаётся Fact без текстовой привязки.

## Контракт архива и адаптеров

`CourseSnapshot` — вход/выход storage adapter. Archive adapter обязан сериализовать `manifest.json`, `course.json`, `notes/<id>.md`, `facts/<id>.md`, `assets/<id>.<ext>` по ADR-001; импорт валидирует полностью в staging до публикации. Обязательны diagnostics: `unsupportedSchemaVersion`, `unsafeArchive`, `checksumMismatch`, `invalidStructure`, `courseConflict`, `revisionConflict`, `courseMismatch`, `invalidEdge`. Невалидный текстовый URL не относится к `invalidStructure`.

## Последствия

Публичные Python fixtures и contract tests находятся в `synopsis_domain/` и `tests/`; это исполнимый oracle, а не production server. S02 выбирает реализацию адаптеров, сохранив поля и семантику. S03 обязан отличать draft от saved revision; S04 реализует CourseRoot и геометрию; S06 реализует ZIP/лимиты/diagnostics.
