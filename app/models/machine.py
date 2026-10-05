"""Конфигурация косовалковой правильной машины."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class MachineConfig:
    """Пределы и параметры демо-машины.

    Значения загружаются из ``data/recipes.json`` (секция ``machine``),
    поэтому конфигурацию можно менять без правки кода.
    """

    name: str
    min_diameter: float
    max_diameter: float
    min_gap: float
    max_gap: float
    roller_count: int

    def supports_diameter(self, diameter: float) -> bool:
        """Проверяет, попадает ли диаметр в рабочий диапазон машины."""
        return self.min_diameter <= diameter <= self.max_diameter

    def clamp_gap(self, gap: float) -> float:
        """Ограничивает уставку рабочим диапазоном машины."""
        return max(self.min_gap, min(self.max_gap, gap))

    def is_gap_clamped(self, gap: float) -> bool:
        """Показывает, выходит ли уставка за пределы машины."""
        return gap < self.min_gap or gap > self.max_gap

    def to_dict(self) -> dict[str, object]:
        """Представление для отчётов и журнала."""
        return {
            "name": self.name,
            "min_diameter": self.min_diameter,
            "max_diameter": self.max_diameter,
            "min_gap": self.min_gap,
            "max_gap": self.max_gap,
            "roller_count": self.roller_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "MachineConfig":
        """Создаёт конфигурацию из секции ``machine`` файла рецептов."""
        return cls(
            name=str(data.get("name", "Косовалковая машина")),
            min_diameter=float(data.get("min_diameter", 20.0)),
            max_diameter=float(data.get("max_diameter", 89.0)),
            min_gap=float(data.get("min_gap", 10.0)),
            max_gap=float(data.get("max_gap", 50.0)),
            roller_count=int(data.get("roller_count", 3)),
        )