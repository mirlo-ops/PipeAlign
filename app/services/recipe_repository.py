"""Чтение конфигурации и рецептов из ``data/recipes.json``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.models.machine import MachineConfig
from app.models.pipe import Pipe
from app.utils.paths import bundled_data_path

#: Обязательные ключи верхнего уровня. Их отсутствие означает, что файл
#: рецептов повреждён и приложение должно завершиться с понятной ошибкой.
REQUIRED_SECTIONS: tuple[str, ...] = (
    "machine",
    "materials",
    "operations",
    "base_recipes",
    "deflection_curve",
)


class RecipeError(RuntimeError):
    """Файл рецептов отсутствует, не читается или имеет неверную структуру."""


class RecipeRepository:
    """Загружает и валидирует рецепты, отдаёт готовые объекты моделей.

    Загрузка выполняется один раз и кешируется: справочник марок и
    демо-заказы меняются только при перезапуске приложения.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = Path(path) if path is not None else bundled_data_path()
        self._raw: dict[str, Any] | None = None

    @property
    def path(self) -> Path:
        """Путь к файлу рецептов (для сообщений об ошибке)."""
        return self._path

    @property
    def raw(self) -> dict[str, Any]:
        """Сырые данные рецептов; при первом обращении читаются с диска."""
        if self._raw is None:
            self._raw = self._load()
        return self._raw

    def reload(self) -> None:
        """Принудительно перечитывает файл рецептов."""
        self._raw = None
        _ = self.raw

    def _load(self) -> dict[str, Any]:
        """Читает JSON и проверяет наличие обязательных секций."""
        if not self._path.exists():
            raise RecipeError(f"Файл рецептов не найден: {self._path}")
        try:
            with self._path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except json.JSONDecodeError as exc:
            raise RecipeError(f"Файл рецептов повреждён: {exc}") from exc
        except OSError as exc:
            raise RecipeError(f"Не удалось прочитать файл рецептов: {exc}") from exc

        if not isinstance(data, dict):
            raise RecipeError("Файл рецептов должен содержать объект JSON.")
        missing = [section for section in REQUIRED_SECTIONS if section not in data]
        if missing:
            raise RecipeError(
                "В файле рецептов отсутствуют разделы: " + ", ".join(missing)
            )
        if not isinstance(data["base_recipes"], list) or not data["base_recipes"]:
            raise RecipeError("Раздел base_recipes пуст или имеет неверный формат.")
        return data

    @property
    def machine(self) -> MachineConfig:
        """Конфигурация демо-машины."""
        return MachineConfig.from_dict(self.raw["machine"])

    @property
    def materials(self) -> list[str]:
        """Список марок стали для выпадающего списка."""
        return [str(item["id"]) for item in self.raw["materials"]]

    @property
    def material_properties(self) -> list[dict[str, Any]]:
        """Полные записи справочника марок."""
        return list(self.raw["materials"])

    @property
    def operations(self) -> list[str]:
        """Список технологических операций."""
        return [str(item) for item in self.raw["operations"]]

    @property
    def base_recipes(self) -> list[dict[str, Any]]:
        """Базовые рецепты (диаметр, стенка, зазор)."""
        return list(self.raw["base_recipes"])

    @property
    def deflection_curve(self) -> list[list[float]]:
        """Кривая зависимости компенсации от стрелы прогиба."""
        return [list(point) for point in self.raw["deflection_curve"]]

    @property
    def demo_orders(self) -> list[Pipe]:
        """Демонстрационные заказы из файла рецептов."""
        raw_orders = self.raw.get("demo_orders", []) or []
        return [Pipe.from_dict(item) for item in raw_orders]

    def demo_order(self, order_no: str) -> Pipe | None:
        """Возвращает демо-заказ по номеру, если он есть."""
        for pipe in self.demo_orders:
            if pipe.order_no == order_no:
                return pipe
        return None

    def default_demo_order(self) -> Pipe:
        """Возвращает ДЕМО-002 (основной кейс презентации).

        Если номер отсутствует, берётся первый доступный заказ.
        """
        order = self.demo_order("ДЕМО-002")
        if order is not None:
            return order
        orders = self.demo_orders
        if orders:
            return orders[0]
        raise RecipeError("В файле рецептов нет демо-заказов для показа.")