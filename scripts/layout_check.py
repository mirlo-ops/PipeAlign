"""Проверка вёрстки без участия человека.

Скрипт проверяет, что при минимальном размере окна (1280×720) все
ключевые элементы видимы, не имеют нулевого размера и не выходят за
границы родителя. Нужен как быстрый индикатор вёрстки после правок.

Запуск::

    python scripts/layout_check.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.services.journal_service import JournalService  # noqa: E402
from app.services.recipe_repository import RecipeRepository  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402
from app.utils.paths import style_path  # noqa: E402


def check_widget(window: MainWindow, name: str, widget: object, problems: list[str]) -> None:
    """Проверяет размер и видимость одного виджета."""
    width = widget.width()
    height = widget.height()
    if width <= 0 or height <= 0:
        problems.append(f"{name}: нулевой размер {width}×{height}")
    if not widget.isVisible():
        problems.append(f"{name}: виджет невидим")
    if width < 60:
        problems.append(f"{name}: слишком узкий ({width} px)")


def main() -> int:
    """Прогоняет проверки вёрстки во всех вкладках."""
    application = QApplication(sys.argv)
    application.setApplicationName("PipeAlignLayoutCheck")
    stylesheet = style_path()
    if stylesheet.exists():
        application.setStyleSheet(stylesheet.read_text(encoding="utf-8"))

    window = MainWindow(RecipeRepository(), JournalService())
    window.resize(1280, 720)
    window.show()
    application.processEvents()

    problems: list[str] = []

    # Вкладка «Переналадка»: расчёт, чтобы поля результата были заполнены.
    window._on_calculate()
    application.processEvents()

    for tab_index in range(window.tabs.count()):
        window.tabs.setCurrentIndex(tab_index)
        application.processEvents()
        tab = window.tabs.widget(tab_index)
        check_widget(window, f"вкладка {tab_index}", tab, problems)

    window.tabs.setCurrentIndex(0)
    application.processEvents()

    check_widget(window, "форма ввода", window.input_panel, problems)
    check_widget(window, "схема машины", window.machine_view, problems)
    check_widget(window, "схема (view)", window.machine_view._view, problems)
    check_widget(window, "панель результата", window.result_panel, problems)
    check_widget(window, "журнал сессии", window.session_log, problems)
    check_widget(window, "кнопка расчёта", window.input_panel.calculate_button, problems)
    check_widget(window, "кнопка применения", window.input_panel.apply_button, problems)
    check_widget(window, "кнопка обоснования", window.input_panel.explanation_button, problems)

    if not window.input_panel.apply_button.isEnabled():
        problems.append("кнопка «Применить» заблокирована после расчёта")
    if window.result_panel.final_gap_field.text() == "—":
        problems.append("итоговая уставка не показана после расчёта")

    # Схема: валки должны находиться внутри сцены.
    scene = window.machine_view._scene
    scene_rect = scene.sceneRect()
    for index, roller in enumerate(window.machine_view._rollers):
        if not scene_rect.contains(roller.rect()):
            problems.append(f"валок №{index + 1} вышел за границы сцены: {roller.rect()}")

    print(f"Проверено элементов схемы: {len(window.machine_view._rollers)}")
    print(f"Размер окна: {window.width()}×{window.height()}")
    print(f"Размер схемы: {scene_rect.width():.0f}×{scene_rect.height():.0f}")

    if problems:
        print("\nПРОБЛЕМЫ ВЁРСТКИ:")
        for item in problems:
            print(f"  - {item}")
        return 1

    print("\nВЁРСТКА КОРРЕКТНА")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())