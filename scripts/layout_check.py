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

from app.services.auth_service import Session, authenticate  # noqa: E402
from app.services.journal_service import JournalService  # noqa: E402
from app.services.recipe_repository import RecipeRepository  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402
from app.utils.paths import style_path  # noqa: E402


#: Учётные записи, под которыми проверяется вёрстка.
#: Оператор проверяется первым: у него скрыты самые широкие блоки, поэтому
#: именно его вёрстка — самая строгая проверка минимального размера окна.
ACCOUNTS_TO_CHECK: tuple[tuple[str, str, str], ...] = (
    ("akulov", "1234", "оператор"),
    ("korablev", "4321", "контролёр ОТК"),
)


def make_session(login: str, password: str) -> Session:
    """Создаёт сессию для проверки вёрстки."""
    session = authenticate(login, password)
    if session is None:
        raise SystemExit(f"Учётная запись {login} не найдена")
    return session


def check_widget(name: str, widget: object, problems: list[str]) -> None:
    """Проверяет размер и видимость одного виджета."""
    width = widget.width()
    height = widget.height()
    if width <= 0 or height <= 0:
        problems.append(f"{name}: нулевой размер {width}×{height}")
    if not widget.isVisible():
        problems.append(f"{name}: виджет невидим")
    if width < 60:
        problems.append(f"{name}: слишком узкий ({width} px)")


def check_role_layout(
    application: QApplication, login: str, password: str, role_label: str
) -> list[str]:
    """Проверяет вёрстку главного окна под одной ролью.

    Возвращает список замечаний: пустой список означает, что под этой
    ролью вёрстка корректна.
    """
    problems: list[str] = []

    window = MainWindow(RecipeRepository(), JournalService(), make_session(login, password))
    window.resize(1280, 720)
    window.show()
    application.processEvents()

    # Вкладка «Переналадка»: расчёт, чтобы поля результата были заполнены.
    window._on_calculate()
    application.processEvents()

    for tab_index in range(window.tabs.count()):
        window.tabs.setCurrentIndex(tab_index)
        application.processEvents()
        tab = window.tabs.widget(tab_index)
        check_widget(f"{role_label}: вкладка {tab_index}", tab, problems)

    window.tabs.setCurrentIndex(0)
    application.processEvents()

    check_widget(f"{role_label}: форма ввода", window.input_panel, problems)
    check_widget(f"{role_label}: схема машины", window.machine_view, problems)
    check_widget(f"{role_label}: схема (view)", window.machine_view._view, problems)
    check_widget(f"{role_label}: панель результата", window.result_panel, problems)
    check_widget(f"{role_label}: журнал сессии", window.session_log, problems)
    check_widget(
        f"{role_label}: кнопка расчёта",
        window.input_panel.calculate_button,
        problems,
    )
    check_widget(
        f"{role_label}: кнопка применения",
        window.input_panel.apply_button,
        problems,
    )
    check_widget(
        f"{role_label}: кнопка обоснования",
        window.result_panel.explanation_button,
        problems,
    )

    if not window.input_panel.apply_button.isEnabled():
        problems.append(f"{role_label}: кнопка «Применить» заблокирована после расчёта")
    if window.result_panel.final_gap_field.text() == "—":
        problems.append(f"{role_label}: итоговая уставка не показана после расчёта")

    # Права роли: скрытые блоки не должны попадать на экран.
    session = window._session
    if window.input_panel._order_box.isVisible() != session.show_order_form:
        problems.append(f"{role_label}: видимость «Заказ и операция» не по правам")
    if window.result_panel._effect_box.isVisible() != session.show_effect_panel:
        problems.append(f"{role_label}: видимость «Ожидаемый эффект» не по правам")

    # Схема: валки должны находиться внутри сцены.
    scene = window.machine_view._scene
    scene_rect = scene.sceneRect()
    for index, roller in enumerate(window.machine_view._rollers):
        if not scene_rect.contains(roller.rect()):
            problems.append(
                f"{role_label}: валок №{index + 1} вышел за границы сцены: "
                f"{roller.rect()}"
            )

    print(f"  {role_label}: схема {scene_rect.width():.0f}×{scene_rect.height():.0f}, "
          f"окно {window.width()}×{window.height()}, "
          f"уставка {window.result_panel.final_gap_field.text()}")

    window.close()
    return problems


def main() -> int:
    """Прогоняет проверки вёрстки во всех вкладках и под обеими ролями."""
    application = QApplication(sys.argv)
    application.setApplicationName("PipeAlignLayoutCheck")
    stylesheet = style_path()
    if stylesheet.exists():
        application.setStyleSheet(stylesheet.read_text(encoding="utf-8"))

    problems: list[str] = []
    print("Проверяется вёрстка под каждой ролью:")
    for login, password, role_label in ACCOUNTS_TO_CHECK:
        problems.extend(check_role_layout(application, login, password, role_label))

    if problems:
        print("\nПРОБЛЕМЫ ВЁРСТКИ:")
        for item in problems:
            print(f"  - {item}")
        return 1

    print("\nВЁРСТКА КОРРЕКТНА")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())