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
from app.models.machine import MachineConfig  # noqa: E402
from app.services.auth_service import Session  # noqa: E402
from app.services.journal_service import JournalService  # noqa: E402
from app.services.recipe_repository import RecipeError, RecipeRepository  # noqa: E402
from app.ui.login_dialog import LoginDialog  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402
from app.utils.paths import style_path  # noqa: E402





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
    """Создаёт приложение и работает в цикле «вход — работа — смена входа»."""
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

    while True:
        session = request_login(repository.machine)
        if session is None:
            # Пользователь закрыл окно входа: выходим без сообщения
            # об ошибке. Это нормальный исход, а не сбой.
            return 0

        if not run_session(application, repository, session):
            return 0


def run_session(
    application: QApplication, repository: RecipeRepository, session: Session
) -> bool:
    """Открывает главное окно и ждёт либо выход из программы, либо смену входа.

    Возвращает ``True``, если нужно вернуться к окну входа, и ``False``,
    если пользователь закрыл программу. Окно пересоздаётся на каждой
    итерации: права и подпись сотрудника задаются в конструкторе, поэтому
    смена пользователя не должна оставлять в интерфейсе следов прежнего.
    """
    from PySide6.QtCore import QEventLoop

    window = MainWindow(repository, JournalService(), session)

    # Локальный цикл событий вместо `application.exec()`: он нужен, чтобы
    # отличить «закрыли окно» от «просили сменить пользователя» — оба
    # случая выглядят одинаково, если слушать `application.exec()`.
    loop = QEventLoop()
    switch_user = {"requested": False}

    def on_logout() -> None:
        switch_user["requested"] = True
        loop.quit()

    window.logoutRequested.connect(on_logout)
    window.show()
    loop.exec()
    window.close()

    if switch_user["requested"]:
        return True

    return False


def request_login(machine: MachineConfig) -> Session | None:
    """Показывает окно входа и возвращает сессию сотрудника.

    Отмена входа — это нормальный исход, а не сбой, поэтому возвращается
    ``None``, и ``main()` завершает работу без диалога об ошибке.
    """
    dialog = LoginDialog(machine)
    if dialog.exec() != LoginDialog.DialogCode.Accepted:
        return None
    return dialog.session()


if __name__ == "__main__":
    raise SystemExit(main())