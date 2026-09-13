# Отчёт S05 — выделение, факты и источники

## Состояние

- Этап: S05.
- Владелец: `/root/s05_links_facts_sources`.
- Статус: независимые adapter/API и модульные проверки готовы; browser host и реальная карта требуют интеграции владельцами S02/S04.
- Область изменений: `selection/`, `facts/`, `source_links/`, `tests/test_s05_links_facts_sources.py`, этот отчёт.

## Результат

`selection` принимает только один явный `render.SourceSpan` S03. Он проверяет
точные Unicode offsets, отображённый текст, raw-текст и `expectedRevision` до
единственного source patch. Cross-span, formula/code/link/Markdown selections
не имеют SourceSpan и получают `SelectionError` без записи. Поиск целей
ограничен текущим `CourseService` и включает Note без Card. Создание ссылки не
создаёт Edge.

`create_note_from_selection` — adapter над атомарной доменной командой
ADR-002. Он требует от map host явный конечный `FreeCardPlacement`; не
вычисляет раскладку и не создаёт Edge. Ошибка до команды не меняет snapshot,
а ошибка внутри команды откатывается `CourseService`.

`facts` создаёт Fact и marker-link в общей атомарной границе. Fact имеет
строго одного owner Note; индекс прикреплений пересчитывается из Markdown
только owner-а, поэтому чужой `synopsis://fact/...` не раскрывает его. После
удаления marker Fact обнаруживается в `orphan_facts` и сохраняется.

`source_links` допускает только course-scoped `application/pdf` Asset,
проверяет page от 1 и верхнюю границу при известном page count. Оно возвращает
`ExternalPdfIntent(target="_blank", embedded=False)` с best-effort `#page=N`:
никакого iframe, canvas или встроенного viewer нет. Внешний обработчик может
не поддержать fragment; UI обязан показать номер страницы и всё равно открыть
файл. `attach_pdf_to_lecture` проверяет lecture и Source в одной команде;
замена предполагает другой Source, не смену байтов у уже связанного ID.

## Проверки

```powershell
python -m unittest -v tests/test_s05_links_facts_sources.py tests/test_contracts.py tests/test_editor.py tests/test_foundation.py
# Ran 19 tests ... OK

git diff --check
# no errors
```

S05 tests доказывают: точечную замену второй из одинаковых фраз; поиск
cardless target; stale revision и unsupported selection без write; атомарное
создание Note/Card/link без Edge; lifecycle Fact, foreign Fact owner; PDF
page/media validation и external-only intent.

## Gate и ограничения

AC-09, AC-17–18, AC-20–21 и data-часть AC-19/22–23 покрыты модульно.
Реальный browser E2E честно не выполнен: S02 server/shell пока не подключает
S03 renderer и не предоставляет read-mode selection/save host. Финальная
визуальная проверка новой Card в свободном месте (AC-12/19) зависит от S04:
S05 передаёт явный placement, но не имитирует карту. После подключения нужно
вручную проверить browser Range→S03 span (включая UTF-16 adaptation), visible
placement и внешнее открытие PDF в принятом браузере.
