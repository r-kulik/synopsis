# Отчёт S02 — локальная основа

## Состояние

- Этап: S02 — локальная основа приложения.
- Владелец: агент основы `/root/s02_foundation`; интеграция остаётся за `/root`.
- Статус: реализовано и проверено на Windows / CPython 3.14.

## Результат

Реализован запускаемый без Node и без внешних зависимостей localhost baseline. `python -m server.http_server` привязывается только к `127.0.0.1`, отдаёт главную с курсами и рабочее пространство с изменяемым разделителем, вкладочной областью и каталогом конспектов. Тела редактора и карты явно оставлены точками подключения S03/S04.

`FileCourseStorage` сохраняет `CourseSnapshot` S01 как JSON в `<data-dir>/courses/<courseId>.json`; вложения хранятся в `<data-dir>/assets/<courseId>/<assetId>`. Запись снимка идёт через fsync временного файла и `os.replace`, поэтому неудачная замена не подменяет последнюю сохранённую версию. Assets выдаются только маршрутом с course ID и проверкой metadata того же курса.

## Запуск

```powershell
python -m server.http_server --data-dir .synopsis-data --port 8765
# открыть http://127.0.0.1:8765/
```

Зависимостей, manifest и lockfile не добавлено: baseline использует только Python standard library. Директория `.synopsis-data/` намеренно локальна и исключена из Git.

## Проверки

```powershell
python -m unittest -v tests/test_contracts.py tests/test_foundation.py
# Ran 11 tests ... OK

git diff --check
# no errors

# separate loopback process; GET / and GET /api/courses returned 200
```

Новые S02 tests подтверждают: (1) курс, карточка-независимый конспект и lecture snapshot переживают новый `FileCourseStorage`; (2) искусственная ошибка `os.replace` возвращает `StorageWriteError`, оставляя байты предыдущего snapshot неизменными; (3) asset доступен своему курсу и недоступен второму.

## Прослеживаемость

| Gate | Результат |
| --- | --- |
| AC-01 | Главная создаёт и открывает курс через loopback API. |
| AC-02 | API и storage всегда получают `courseId`; asset доступа другого курса не имеет. |
| AC-03/04 (данные) | `SynopsisApplication` создаёт Course/Note/Card/Lecture и сохраняет единый snapshot. |
| AC-14 | Две resizable области плюс library/tabs host существуют; editor/map не имитируются. |
| AC-24 | Список, поиск title/summary и фильтр «Without card» работают в shell. |
| AC-27 | Атомарная замена и restart покрыты тестами. |

## Передача и ограничения

S03 использует `SynopsisApplication.save_markdown(course_id, note_id, markdown, revision)` и не должен хранить saved Markdown в UI state. S04 использует `snapshot()` и command boundary для Card/Lecture; визуальная карта пока placeholder. S06 может использовать снимки и course-scoped asset bytes, но ZIP import/export, лимиты и архивные diagnostics не входят в S02.

В этом baseline нет полноценного Markdown editor/render, SVG-карты/рёбер, PDF viewer, archive transfer, upload UI, миграций или межпроцессной блокировки. Одновременная запись двумя server processes пока не поддерживается.
