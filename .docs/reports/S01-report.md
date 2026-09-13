# Отчёт S01 — модель, команды и контракты

## Состояние

- Этап: S01.
- Исполнитель и интегратор: `/root`.
- Статус: принят.
- База проверки: commit `918ad7f` плюс принятые незакоммиченные результаты S00 и файлы S01.

## Результат

Создан независимый от UI контракт `synopsis_domain`: сущности Course/Note/Card/LectureBox/Edge/Fact/Source/Asset, типизированные ID, URL parser/generator, диагностируемые ошибки и атомарные доменные команды. `tests/test_contracts.py` является общей fixture-проверкой для будущих владельцев редактора, карты и переноса. ADR-002 фиксирует D-04–09, D-12 и D-15.

## Прослеживаемость

| FR / AC | Статус | Доказательство или воспроизведение |
| --- | --- | --- |
| FR-004, FR-075 / AC-02 | Выполнено на domain уровне | `test_course_isolation_and_edge_matrix` отвергает другой courseId; `test_dangling_or_foreign_url...` безопасно не разрешает чужую/отсутствующую цель. |
| FR-021–023, FR-025 / AC-06, AC-07 | Выполнено на domain уровне | Матрица `EDGE_ENDPOINTS`; hierarchy допускает цикл из нескольких Card, запрещает несовместимые типы/self-loop. |
| FR-036, FR-076 / AC-13 | Выполнено на domain уровне | `test_lecture_box_removal...`: сохраняются Note, Card, мировая позиция; Edge не затрагивается. |
| FR-073, FR-075 / AC-25 | Выполнено на domain уровне | `test_delete_note...`: чужой Markdown не меняется, cardless Note остаётся валиден. |
| FR-048–050 | Выполнено на domain уровне | `test_selection_is_atomic...` и `test_fact_has_exactly_one_owner`; browser source mapping остаётся S03/S05. |

## Проверки

Среда: Windows, PowerShell, CPython 3.14. Команда:

```powershell
python -m unittest -v tests/test_contracts.py
```

Ожидается шесть успешных contract tests. Также воспроизводятся S00 spikes из отчёта S00; они не являются доказательством UI или ZIP adapter S06.

## Решения и ограничения

Принят ADR-002. `CourseSnapshot` — контракт адаптера, но фактические local storage, ZIP limits, JSON schema validation и browser UI намеренно не реализованы на S01. Raw offsets для selection — контракт команды; достоверное DOM-to-source сопоставление по-прежнему обязан доказать S03. URL parser не проверяет существование цели: это обязанность course-scoped resolver при открытии ссылки.

## Передача следующему этапу

S02 может реализовать server/storage adapter за `CourseSnapshot` и `CourseService`; не менять поля/семантику без ADR. S03 использует `save_markdown(noteId, markdown, expectedRevision)`. S04 использует Edge.geometry и правила матрицы. S05 использует `create_note_from_selection` и `create_fact`. S06 использует schemaVersion, snapshot и ADR-002 diagnostics.

## Проверка интегратором

Дата: 2026-09-13. Интегратор воспроизвёл `python -m unittest -v tests/test_contracts.py` (8/8), все три S00 spike и `git diff --check`. Gate S01 принят: доменные контракты достаточны для S02–S06; browser/UI проверки не относятся к этому этапу.
