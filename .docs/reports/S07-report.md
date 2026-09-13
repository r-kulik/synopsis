# S07 — интеграция

> Этот отчёт описывает прежнюю сборку. Текущий отдельный HTML/JS/CSS-интерфейс
> и его браузерные проверки описаны в [UI-recovery-report.md](UI-recovery-report.md).

## Результат

Добавлен реально запускаемый stdlib localhost host: `server/http_server.py` и
`shell/page.py` используют публичные API editor/render, `MapCommands`,
`CourseService`, selection/facts и transfer. Это не placeholder: HTTP routes
сохраняют Markdown с revision, выполняют map commands, bounded selection
commands, удаление Note, export/import и возвращают диагностические ошибки.

UI даёт каталог/поиск cardless Note, вкладки с черновиками, raw/read switch,
SVG-карту с drag карточек, снятие/восстановление карточки, снятие рамки,
экспорт/импорт. Лекции создаются как Note+LectureBox.

## Проверки

```powershell
python -m unittest -v tests/test_contracts.py tests/test_foundation.py tests/test_editor.py map.tests.test_map tests/test_s05_links_facts_sources.py tests/test_transfer.py
# Ran 33 tests ... OK
python -m unittest -v tests/test_s07_http.py
# Ran 1 test ... OK
python -m server.http_server --data-dir .synopsis-data --port 8765
# http://127.0.0.1:8765/
```

`test_s07_http.py` запускает отдельный localhost процесс и проверяет create,
save, stale revision (400), remove/show Card, ZIP export/import и corrupt ZIP
(400) без публикации. Базовые tests покрывают write failure, missing asset,
course isolation, bounded selection/facts и geometry/restart.

## Gate

Data/HTTP: AC-02, AC-09, AC-13, AC-19, AC-24–27 подтверждены. AC-14 частично:
вкладки и dirty drafts реализованы в browser JS, но автоматизированной browser
проверки нет. AC-31 соблюдён (нет AI/sections/collaboration/collapse).

## Ограничения

Настоящий browser E2E не выполнен: доступна только controlled localhost HTTP
проверка. UI намеренно не реализует полноценное DOM Range→Unicode span
преобразование, редактор facts/source PDF forms и визуальное редактирование
edge control-points; их безопасные публичные HTTP command routes существуют,
но UI требует S08 browser QA. Это не заявляется как выполнение этих AC.
