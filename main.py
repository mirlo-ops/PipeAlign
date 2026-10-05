"""PipeAlign / ТрубоНастрой — точка входа.

Запуск: ``python main.py``.

Приложение полностью автономно: подключается только к локальному JSON,
сетевых обращений нет. Все ошибки старта обрабатываются и показываются
понятным сообщением вместо трассировки в консоль.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Каталог проекта добавляется в путь импорта, чтобы приложение стартовало
# как из исходников, так и из произвольного рабочего каталога.
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import (  # noqa: E402
    APP_INTERNAL_NAME,
    APP_ORGANISATION,
    APP_VERSION,
    DISCLAIMER,
)
from app.services.journal_service import JournalService  # noqa: E402
from app.services.recipe_repository import RecipeError, RecipeRepository  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402
from app.utils.paths import style_path  # noqa: E402


def configure_high_dpi() -> None:
    """Включает масштабирование под высокое разрешение.

    В Qt 6 политики включены по умолчанию, поэтому настройка
    выполняется только если атрибут ещё существует.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication

    if hasattr(Qt.ApplicationAttribute, "AA_UseHighDpiPixmaps"):
        QGuiApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    if hasattr(Qt.ApplicationAttribute, "AA_EnableHighDpiScaling"):
        QGuiApplication.setAttribute(
            Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True
        )


def load_stylesheet() -> str:
    """Читает тему оформления из ресурсов приложения."""
    path = style_path()
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        # Тема необязательна: без неё приложение работает со стилем Qt.
        return ""


def report_startup_error(title: str, message: str) -> None:
    """Показывает ошибку запуска и завершает приложение."""
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        app = QApplication.instance() or QApplication(sys.argv)
        app.setApplicationName(APP_INTERNAL_NAME)
        box = QMessageBox()
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle(f"{APP_INTERNAL_NAME} — ошибка запуска")
        box.setText(title)
        box.setInformativeText(message)
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.exec()
    except Exception:  # noqa: BLE001 - если Qt недоступен, пишем в stderr
        print(f"[{title}] {message}", file=sys.stderr)
    sys.exit(1)


def main() -> int:
    """Создаёт приложение, главное окно и запускает цикл событий."""
    configure_high_dpi()

    from PySide6.QtWidgets import QApplication

    application = QApplication(sys.argv)
    application.setApplicationName(APP_INTERNAL_NAME)
    application.setApplicationDisplayName(f"{APP_INTERNAL_NAME} · {APP_VERSION}")
    application.setOrganizationName(APP_ORGANISATION)
    application.setDesktopFileName(APP_INTERNAL_NAME)

    stylesheet = load_stylesheet()
    if stylesheet:
        application.setStyleSheet(stylesheet)

    try:
        repository = RecipeRepository()
        repository.machine  # Проверяем файл рецептов до создания окна.
    except RecipeError as exc:
        report_startup_error(
            "Не удалось загрузить рецепты",
            f"{exc}\n\nПроверьте наличие файла data/recipes.json рядом с программой.\n"
            f"{DISCLAIMER}",
        )
        return 1

    journal = JournalService()
    window = MainWindow(repository, journal)
    window.show()

    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())