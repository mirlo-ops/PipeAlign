"""Работа с файловой системой: ресурсы приложения и каталог данных.

Модуль учитывает два режима запуска:

* из исходников — ресурсы лежат рядом с проектом;
* из собранного PyInstaller-бинарника — ресурсы распаковыны во временный
  каталог ``sys._MEIPASS``.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

#: Внутреннее имя приложения, используется для имени каталога данных.
APP_DIR_NAME = "PipeAlign"


def is_frozen() -> bool:
    """Работает ли приложение из собранного бинарника."""
    return bool(getattr(sys, "frozen", False))


def resource_path(relative_path: str) -> Path:
    """Возвращает абсолютный путь к ресурсу приложения.

    Работает и при запуске из исходников, и в собранном ``.exe``:
    при заморозке путь строится от ``sys._MEIPASS``.
    """
    relative = Path(relative_path)
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass) / relative
    project_root = Path(__file__).resolve().parents[2]
    candidate = project_root / relative
    if candidate.exists():
        return candidate
    # Резервный вариант: ресурс лежит рядом с пакетом app/.
    return Path(__file__).resolve().parent.parent / relative


def style_path() -> Path:
    """Путь к файлу темы оформления."""
    return resource_path("app/resources/styles.qss")


def bundled_data_path() -> Path:
    """Путь к файлу рецептов ``data/recipes.json`` внутри ресурсов."""
    return resource_path("data/recipes.json")


def app_data_dir() -> Path:
    """Каталог для записи журнала и резервных копий.

    Порядок выбора: ``%APPDATA%/PipeAlign``, затем ``~/.config/PipeAlign``,
    затем системный временный каталог. Каталог создаётся при необходимости.
    """
    candidates: list[Path] = []

    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.append(Path(appdata) / APP_DIR_NAME)

    home = Path.home()
    candidates.append(home / ".config" / APP_DIR_NAME)

    candidates.append(Path(tempfile.gettempdir()) / APP_DIR_NAME)

    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / ".write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return candidate
        except (OSError, PermissionError):
            continue

    # Теоретически недостижимый веткой: временный каталог всегда доступен.
    fallback = Path(tempfile.gettempdir()) / APP_DIR_NAME
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def journal_path() -> Path:
    """Путь к основному файлу журнала."""
    return app_data_dir() / "journal.json"


def log_directory() -> Path:
    """Каталог с журналом (используется в окне «О системе»)."""
    return app_data_dir()