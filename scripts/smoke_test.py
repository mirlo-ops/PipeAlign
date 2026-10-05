"""Прогон интерфейса без показа окна.

Скрипт создаёт QApplication в offscreen-режиме, открывает главное окно
и имитирует действия пользователя: загрузку заказа, расчёт, применение,
открытие отчёта и журнала. Нужен для проверки, что интерфейс собирается
и все слоты отрабатывают без исключений.

Запуск::

    QT_QPA_PLATFORM=offscreen python scripts/smoke_test.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.services.auth_service import Session, authenticate  # noqa: E402
from app.services.journal_service import JournalService  # noqa: E402
from app.services.recipe_repository import RecipeRepository  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402
from app.utils.paths import style_path  # noqa: E402


def make_session(login: str, password: str) -> Session:
    """Создаёт сессию для прогона интерфейса."""
    session = authenticate(login, password)
    if session is None:
        raise SystemExit(f"Учётная запись {login} не найдена")
    return session


def pump(application: QApplication, times: int = 6) -> None:
    """Прогоняет очередь событий, чтобы отработали таймеры и анимации."""
    for _ in range(times):
        application.processEvents()


def main() -> int:
    """Выполняет сценарий проверки интерфейса."""
    application = QApplication(sys.argv)
    application.setApplicationName("PipeAlignSmokeTest")
    stylesheet = style_path()
    if stylesheet.exists():
        application.setStyleSheet(stylesheet.read_text(encoding="utf-8"))

    repository = RecipeRepository()
    journal = JournalService()
    session = make_session("korablev", "4321")
    window = MainWindow(repository, journal, session)
    window.show()
    pump(application)

    print(f"1. Вход: {session.operator_name}, роль «{session.role_title}»")
    print("   Демо-заказ ДЕМО-002 в форме:", window.input_panel.collect())

    window._on_calculate()
    pump(application)
    result = window._result
    if result is None:
        print("ОШИБКА: расчёт не вернул результат")
        return 1
    print(
        "2. Расчёт: базовая={} материал={} изгиб={} итог={} проходов={} "
        "скорость={} риск={}".format(
            result.base_gap,
            result.material_correction,
            result.deflection_correction,
            result.final_gap,
            result.passes,
            result.feed_speed,
            result.risk_level,
        )
    )
    if abs(result.final_gap - 30.7) > 0.05:
        print("ОШИБКА: ожидалась итоговая уставка 30.7 мм")
        return 1

    window._on_apply()
    pump(application)
    print("3. Настройка применена, записей в журнале:", len(journal.load()))

    window.input_panel.diameter_spin.setValue(48.0)
    window.input_panel.parametersChanged.emit()
    pump(application)
    print("4. После смены диаметра доступно применение:", window.input_panel.apply_button.isEnabled())
    print("   Статус:", window.status_label.text())

    window._on_calculate()
    pump(application)
    print("5. Расчёт для Ø48 мм:", window._result.final_gap, "мм,", window._result.passes, "прохода")

    window.input_panel.apply_preset("bent_pipe")
    window._on_calculate()
    pump(application)
    print("6. Пресет «труба погнулась после гибки»:", window._result.final_gap, "мм")

    window.tabs.setCurrentIndex(1)
    pump(application)
    print("7. Вкладка «Отчёт» построена, строк сравнения:", window.report_tab.comparison_table.rowCount())

    window.tabs.setCurrentIndex(2)
    pump(application)
    print("8. Вкладка «Журнал» построена, строк:", window.journal_tab.table.rowCount())

    window.tabs.setCurrentIndex(3)
    pump(application)
    print("9. Вкладка «О системе» построена")

    # Модальные диалоги здесь не открываются: exec() блокирует очередь
    # событий. Проверяем вместо этого расчётную часть, которую они вызывают.
    from app.core.calculator import apply_manual_correction, calculate_settings
    from app.services.report_service import estimate_operator_mistake

    pipe = window.input_panel.collect()
    result = calculate_settings(pipe, repository.machine, repository.raw)
    stale_gap = window._stale_gap_for(pipe)
    estimate = estimate_operator_mistake(result, stale_gap)
    print(
        "10. Симуляция ошибки наладчика: оставлено {}, правильно {}, брак {} %".format(
            stale_gap, result.final_gap, estimate["defect_percent"]
        )
    )

    manual = apply_manual_correction(pipe, repository.machine, repository.raw, 31.5, "проверка")
    window.result_panel.show_result(manual, pipe.required_straightness)
    window.machine_view.mark_manual()
    pump(application)
    print("11. Ручная коррекция применена, итог:", manual.final_gap, "мм")

    # Имена файлов выгрузки строятся заранее, до открытия диалога сохранения.
    suggested = window.report_tab._suggested_name(pipe.order_no)
    plain = window.report_tab._suggested_name(pipe.order_no, "txt")
    print("12. Имена выгрузки:", suggested, "|", plain)

    print("13. Журнал сохранён в:", journal.path)

    # Смена пользователя: окно входа модальное, поэтому проверяем то,
    # что не требует диалога — сигнал выхода и чистоту нового окна.
    fired: list[str] = []
    window.logoutRequested.connect(lambda: fired.append("выход"))
    window._finish_scenario()
    window.logoutRequested.emit()
    print("14. Сигнал смены пользователя:", "получен" if fired else "НЕ ПОЛУЧЕН")

    operator = MainWindow(repository, JournalService(), make_session("akulov", "1234"))
    operator.show()
    pump(application)
    print("15. Новое окно оператора:", operator.user_label.text())
    print(
        "    «Заказ и операция» скрыта:",
        not operator.input_panel._order_box.isVisible(),
    )
    operator._on_calculate()
    pump(application)
    print("    уставка оператора:", operator._result.final_gap, "мм")

    print("ПРОВЕРКА ПРОЙДЕНА")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())