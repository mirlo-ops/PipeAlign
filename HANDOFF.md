# HANDOFF — контекст проекта PipeAlign / ТрубоНастрой

Документ для передачи другому агенту или разработчику. Он описывает, **что уже
сделано**, **как это устроено** и **как проверять изменения**. Проект рабочий,
собирается в `.exe`, все проверки зелёные.

---

## 1. Что это за проект

**PipeAlign / ТрубоНастрой** — демонстрационный ассистент переналадки
косовалковой (диагонально-валковой) правильной машины для труб. По параметрам
трубы (диаметр, стенка, марка стали, операция, остаточный изгиб) программа
считает уставку зазора между валками, число проходов, скорость подачи,
объясняет решение человеческим языком и оценивает экономию времени против
ручной переналадки.

Назначение — **защита дипломного/курсового проекта и демонстрация на
производстве**. Поэтому в интерфейсе обязательно висит дисклеймер:

> Демонстрационный прототип. Расчёты модельные. Реальное управление
> оборудованием требует отдельной валидации.

Вымышленное производство: ООО «СтальТрубПром». Программа **ничего не
управляет**: ни обращений к станку, ни сети, ни файлов вне `%APPDATA%`.

## 2. Жёсткие требования (нарушать нельзя)

| Требование | Как выполнено |
|---|---|
| Python 3.10+, PySide6, **только QtWidgets** | QML не используется вообще |
| PyInstaller, JSON, только stdlib | `json`, `csv`, `dataclasses`, `datetime`, `pathlib`, `sys` |
| Полные файлы, без TODO / pass / NotImplemented | проверено grep'ом, чисто |
| Типизация, dataclasses, слоистая архитектура | `from __future__ import annotations`, хинты everywhere |
| Идентификаторы английские, UI и комментарии русские | соблюдается во всех файлах |
| Запуск `python main.py` | корень проекта = рабочий каталог, доп. вложенности нет |
| Сборка `scripts/build_windows.bat` | проверено, `.exe` запускается |
| 4 вкладки: Переналадка, Отчёт, Журнал, О системе | `MainWindow` + 4 виджета |
| Окно не меньше 1280×720, тёмная промышленная тема | `styles.qss`, проверяется `layout_check.py` |
| Запрещено: Flask, FastAPI, React, Vue, Electron, WebSocket, HTTP, Docker, SQL | в коде отсутствует |

## 3. Проверочный кейс (зафиксирован тестом `test_demo_case_57x3_5`)

Ø57×3.5, сталь 09Г2С, операция «после гибки», остаточный изгиб 6 мм/м:

| Параметр | Значение |
|---|---|
| Базовая уставка | 29.8 мм |
| Поправка на материал | +0.3 мм |
| Поправка на изгиб | +0.6 мм |
| Итоговая уставка | **30.7 мм** |
| Проходы | 2 |
| Скорость подачи | 11.2 м/мин |
| Прогноз кривизны | 1.2 мм/м |
| Риск | низкий (1.5 балла) |

Если эти числа «поехали» — сломалось ядро, а не интерфейс.

## 4. Структура и архитектура

```
main.py                       QApplication, high-DPI, стили, диалог ошибки старта
requirements.txt              PySide6, pyinstaller, pytest
README.md                     пользовательская документация
.gitignore
data/recipes.json             machine, materials, operations, base_recipes,
                              deflection_curve, demo_orders
app/__init__.py               APP_VERSION, APP_ORGANISATION, DISCLAIMER
app/models/                   dataclasses, Qt-free
  pipe.py                     Pipe (+ from_dict: понимает wall и wall_thickness)
  machine.py                  MachineConfig
  result.py                   CalculationResult, MANUAL_NOTE, copy() через dataclasses.replace
app/core/                     расчётное ядро, Qt-free — поэтому тесты не тянут PySide6
  calculator.py               calculate_settings(), apply_manual_correction(),
                              _fill_effect_estimate(), все демо-коэффициенты
  validation.py               проверка диапазонов, сообщения об ошибках
  explanations.py             текстовые объяснения решения и рисков
app/services/
  recipe_repository.py        загрузка data/recipes.json, RecipeError
  journal_service.py          журнал: статусы, COLUMNS, aggregates(), csv_rows(),
                              _quarantine_broken_file()
  report_service.py           comparison_rows(), build_summary(),
                              estimate_operator_mistake(), write_csv(), build_report_text()
app/utils/
  paths.py                    %APPDATA%/PipeAlign → fallback ~/.config → temp;
                              style_path() ищет и исходник, и _MEIPASS (PyInstaller)
  formatting.py               русские единицы измерения: мм, м/мин, баллы риска
app/ui/
  main_window.py              4 вкладки, _guard() — единая обёртка исключений,
                              демо-сценарий по таймерам, _stale_gap_for()
  input_panel.py              форма, сигналы (в т.ч. explanationRequested),
                              apply_preset(), _select_combo()
  machine_view.py             QGraphicsScene схемы машины, OffsetDriver(Property),
                              AnimatedRollers, MachineView
  result_panel.py             уставка, проходы, скорость, риск, ручная коррекция
  report_tab.py               карточки, сравнение «как есть / как будет»,
                              агрегаты журнала, экспорт CSV/TXT
  journal_tab.py              таблица записей, фильтры, экспорт
  about_tab.py                дисклеймер, версии, возможности, ограничения
  dialogs.py                  модальные диалоги (детали расчёта, объяснение)
app/resources/styles.qss      тёмная тема; object names: #PrimaryButton, #SuccessButton,
                              #DangerButton, #RiskLow/Medium/High, #Disclaimer, #DemoBadge
scripts/
  run_windows.bat             запуск из исходников
  build_windows.bat           сборка .exe (PyInstaller)
  smoke_test.py               13 шагов сквозной проверки GUI (offscreen)
  render_demo.py              7 PNG-скриншотов в .preview/
  layout_check.py             проверка вёрстки при 1280×720
tests/
  test_calculator.py          ядро, включая демо-кейс
  test_services.py            репозиторий, журнал, отчёты
```

Поток данных: `InputPanel.collect()` → `validation` → `core.calculate_settings()`
→ `core.explanations` → `ResultPanel` + `MachineView` (анимация валков) →
`JournalService`.

## 5. Принятые технические решения (важно не «чинить» обратно)

1. **Ядро не импортирует Qt.** `app/core` и `app/models` — чистый Python.
   Из-за этого `pytest tests -q` работает без графической подсистемы.
2. **`OffsetDriver(QObject)` + `Property`.** `QGraphicsItem` не является
   `QObject`, анимировать его напрямую нельзя — поэтому смещение валков
   реализовано отдельным драйвером.
3. **`from PySide6.QtCore import Property`.** В PySide6 нет `Qt.Property`.
4. **Геометрия схемы:** подписи в левой колонке (x=16), рама машины
   x=200…800, валки на x=300/500/700, сцена 820×476, `fitInView` при ресайзе.
5. **Журнал** — `%APPDATA%/PipeAlign/journal.json`, повреждённый файл
   переименовывается в `journal.bad.json`, а не роняет приложение.
6. **CSV** — `utf-8-sig` + разделитель `;`, иначе русский Excel открывает кракозябры.
7. **Имена выгрузок** — `build_suggested_name()` в `report_tab.py`: небезопасные
   символы заменяются на `_`, добавляется номер заказа
   (`report_setup_ДЕМО-002.csv`). Вызывается через метод
   `_suggested_name(order_no, extension)`.
8. **`.bat` используют `pushd`**, а не `cd /d` — иначе не работают с UNC-путями.
9. **Демо-сценарий** — таймеры 700/1900/3000/4100/5500/6900/8300 мс
   через `_schedule()`; кнопка «Демо-сценарий» проходит по всем вкладкам.

## 6. Как проверять изменения

```bat
python -m pytest tests -q          :: 58 тестов, ожидается "58 passed"
python scripts\smoke_test.py       :: "ПРОВЕРКА ПРОЙДЕНА", печатает 30.7 мм
python scripts\layout_check.py     :: "ВЁРСТКА КОРРЕКТНА"
python scripts\render_demo.py      :: 7 PNG в .preview/
python scripts\build_windows.bat   :: dist\PipeAlign\PipeAlign.exe
```

На машине без экрана/дисплея добавляйте переменные окружения:

```powershell
$env:QT_QPA_PLATFORM="offscreen"   # иначе Qt не поднимется без дисплея
$env:PYTHONIOENCODING="utf-8"      # иначе кириллица в консоли — мусор
```

### Грабли, на которые уже наступали

* **`QMessageBox.exec()` в smoke-тесте блокирует очередь событий.** Модальные
  диалоги в автотестах не открываются: вместо них вызываются напрямую
  `estimate_operator_mistake()` и `apply_manual_correction()`.
* **Правка Python-файлов регулярками через PowerShell один раз испортила
  кириллицу** в `machine_view.py`. Русские файлы безопаснее переписывать
  целиком.
* **`py -3` на машине разработчика указывает на старый Python** (pip 19.0.3,
  максимум PySide6 6.2.4). Реальный интерпретатор:
  `C:\Users\24201182\AppData\Local\Programs\Python\Python314\python.exe`
  (Python 3.14, PySide6 6.11.2, pyinstaller, pytest установлены).
* **Рабочий каталог — UNC-путь** вида
  `\\edu.local\public\studenthomes\24201182\Desktop\Project-One`
  (тот же каталог ещё и как `\\KFSW19S3\studenthomes$\24201182\Desktop\Project-One`).
  `cmd` из такого каталога ругается «CMD.EXE не был запущен с CMD.EXE…
  UNC», поэтому `.bat` приходится звать по абсолютному пути.
* **PyInstaller-флаг `--collect-all PySide6` нужен** в `build_windows.bat`.
  Сборка без него тоже работала, но это проверка скорости, а не штатный сценарий.

## 7. Текущее состояние (на момент передачи)

Готово и проверено:

* все файлы проекта написаны, заглушек нет;
* 58 тестов проходят;
* демо-кейс даёт 30.7 мм / 2 прохода / низкий риск;
* все 4 вкладки строятся, вёрстка корректна при 1280×720;
* `dist/PipeAlign/PipeAlign.exe` собран и запускается;
* README описывает стек, запуск, формулу расчёта и ограничения.

Не сделано / что можно улучшить (по возрастанию трудоёмкости):

1. Настоящая QSS-картинка иконки `assets/icon.ico` — `build_windows.bat`
   подхватит её автоматически, если положить файл рядом с `scripts/`.
2. Скриншоты из `.preview/` не вставлялись в README — визуально стоит
   проверить вёрстку глазами на реальном мониторе.
3. Расчётные коэффициенты в `core/calculator.py` — модельные, под реальную
   машину не калибровались (это осознанно и честно сказано в README и
   вкладке «О системе»).
4. Нет юнит-тестов на `explanations.py` и `utils/formatting.py`.

## 8. Что делать в первую очередь на новом месте

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m pytest tests -q
python main.py
```

Если тесты прошли, а приложение открылось — состояние рабочее, можно
вносить изменения. Перед правками читай раздел 5: там зафиксированы решения,
которые легко сломать по незнанию.