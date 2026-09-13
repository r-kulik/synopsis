# Отчёт S04 — карта знаний

## Состояние

- Этап: S04 — карта знаний.
- Владелец: `/root/s04_map`.
- Статус: domain/view-model часть готова; browser-интеграция намеренно передана интегратору, так как S04 не владеет `shell/` и `server/`.

## Результат

Добавлены изолированные пакеты `map/`, `geometry/` и `map_settings/`:

- `CourseMap.from_snapshot(snapshot)` строит CourseRoot, рамки лекций, карточки с **только** title/summary и видимые рёбра. Markdown не анализируется и не становится источником рёбер.
- `MapCommands` задаёт явные атомарные операции карты. Создание/снятие/воссоздание карточек и снятие лекционной рамки делегируют публичным `CourseService.create_edge/create_card/remove_card/remove_lecture_box`; правила матрицы, цикл и несколько родителей поэтому едины с S01.
- Позиции карточек и рамок — мировые. Перемещение рамки сдвигает прикреплённые карточки на тот же delta. Удаление рамки сохраняет эти координаты и связи.
- `geometry.polyline` реализует D-10: `P = S + u(T-S) + v*perpendicular(T-S)`. Контрольные точки Edge хранятся endpoint-relative в `Edge.geometry`; добавление, перемещение и удаление точки доступны командами.
- `MapSettings` сохраняет в `Course.settings["map"]` фильтр, стили карточек и линий. Фильтр не меняет snapshot и скрывает инцидентное ребро при скрытом конце.

Свободное размещение передаётся как явная world-position в `recreate_card`; карта не применяет автоматическую раскладку и не сдвигает существующие объекты.

## Проверки

Выполнено на Windows / CPython 3.14:

```powershell
python -m unittest -v map.tests.test_map
# Ran 9 tests ... OK

git diff --check
# no errors
```

Проверки покрывают: CourseRoot/рамки/видимое содержимое карточки; межлекционную контекстную линию с подписью; все пять типов Edge; допустимый hierarchy-цикл и reject внешнего объекта в hierarchy; движение карточки/рамки; endpoint-relative точки и round-trip exact S02 snapshot serializer; неразрушающий фильтр и стили; отсутствие reflow; снятие/воссоздание Card; снятие рамки с сохранением Note, Edge и world position.

## Правило геометрии

Endpoint для линии — центр Card. Control point сериализуется не в абсолютных координатах, а как `(u, v)` относительно текущих концов; изменение конца автоматически пересчитывает world path. При совпавших endpoints установка новой точки отклоняется диагностируемым `ValueError`, потому что базис направления вырожден.

## Передача интегратору

1. После загрузки `SynopsisApplication.snapshot(course_id)` вызвать `CourseMap.from_snapshot(snapshot)` и отрисовать возвращаемый view model собственным SVG/DOM (без кода React Flow Pro).
2. Pointer drag передавать в `MapCommands.move_card/move_lecture_box`; drag control в `set_control_point`; затем persist `commands.state` существующим S02 storage adapter. Для create/remove использовать `MapCommands`, не прямую мутацию snapshot.
3. Настройки UI передавать через `MapCommands.set_settings`; фильтр — только новый view model, без удаления данных.
4. Для новой карточки host выбирает свободную world-position и вызывает `recreate_card(note_id, position)`. Алгоритм поиска свободного места остался точкой интеграции: этот модуль гарантирует отсутствие reflow, но не измеряет пересечения в браузерном viewport.

## Ограничения

В baseline нет установленного Node/React и S04 не владеет `shell/`/`server/`, поэтому не выполнены browser-level SVG/pointer визуализация, реальные drag handles и persistence HTTP endpoint. Это не заявляется как выполнение финальных AC-03/05–08/10–13: доступны их проверяемые map-model/data основания. Интегратор должен добавить browser E2E после подключения API без изменения геометрического правила.
