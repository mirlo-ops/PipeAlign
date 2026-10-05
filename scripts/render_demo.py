"""Рендер всех вкладок в PNG-файлы для визуальной проверки.

Скрипт создаёт окно, прогревает сценарий расчёта и сохраняет снимки
каждой вкладки в каталог ``.preview``. Нужен, чтобы убедиться, что
тёмная тема и вёрстка выглядят презентационно.

Запуск::

    python scripts/render_demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.services.journal_service import JournalService  # noqa: E402
from app.services.recipe_repository import RecipeRepository  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402
from app.utils.paths import style_path  # noqa: E402

PREVIEW_DIR = PROJECT_ROOT / ".preview"


def capture(window: MainWindow, application: QApplication, name: str) -> None:
    """Сохраняет снимок окна и обрабатывает очередь событий."""
    for _ in range(5):
        application.processEvents()
    QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
    target = PREVIEW_DIR / f"{name}.png"
    window.grab().save(str(target))
    print(f"  сохранено: {target.relative_to(PROJECT_ROOT)}")


def main() -> int:
    """Строит окно и сохраняет снимки всех вкладок."""
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)

    application = QApplication(sys.argv)
    application.setApplicationName("PipeAlignRender")
    stylesheet = style_path()
    if stylesheet.exists():
        application.setStyleSheet(stylesheet.read_text(encoding="utf-8"))

    window = MainWindow(RecipeRepository(), JournalService())
    window.resize(1500, 900)
    window.show()
    application.processEvents()

    print("Снимки вкладок:")
    window.tabs.setCurrentIndex(0)
    capture(window, application, "01_setup_empty")

    window._on_calculate()
    application.processEvents()
    capture(window, application, "02_setup_calculated")

    window._on_apply()
    application.processEvents()
    capture(window, application, "03_setup_applied")

    window.tabs.setCurrentIndex(1)
    application.processEvents()
    capture(window, application, "04_report")

    window.tabs.setCurrentIndex(2)
    application.processEvents()
    capture(window, application, "05_journal")

    window.tabs.setCurrentIndex(3)
    application.processEvents()
    capture(window, application, "06_about")

    # Проверяем, что демо-сценарий прокручивается до конца без зависаний.
    window.tabs.setCurrentIndex(0)
    window._on_demo_scenario()
    finished = False

    def stop_loop() -> None:
        nonlocal finished
        finished = True
        loop.quit()

    loop = QEventLoop()
    QTimer.singleShot(11000, stop_loop)
    QTimer.singleShot(10500, lambda: capture(window, application, "07_scenario_report"))
    loop.exec()

    if finished:
        print("Демо-сценарий отработал: вкладка =", window.tabs.currentIndex())
        print("Статус:", window.status_label.text())
    else:
        print("ВНИМАНИЕ: демо-сценарий не завершился за 11 секунд")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())