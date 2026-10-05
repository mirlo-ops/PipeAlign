"""Параметры трубы — вход расчётного модуля."""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(slots=True)
class Pipe:
    """Исходные данные по одной трубе.

    Значения берутся из формы «Переналадка» или из демо-заказа в recipes.json.
    """

    order_no: str
    batch: str
    operator: str
    diameter: float
    wall_thickness: float
    material: str
    length: float
    operation: str
    has_deflection: bool
    deflection: float
    required_straightness: float

    def copy(self, **changes: object) -> "Pipe":
        """Возвращает копию трубы с применёнными изменениями."""
        return replace(self, **changes)  # type: ignore[arg-type]

    @property
    def designation(self) -> str:
        """Обозначение вида «Ø57×3.5 мм»."""
        return f"Ø{self.diameter:g}×{self.wall_thickness:g} мм"

    @property
    def effective_deflection(self) -> float:
        """Стрела прогиба с учётом флажка «есть изгиб».

        Если изгиб не заявлен, прогиб считается нулевым независимо от
        значения в поле ввода (в UI поле отключается, но данные могут
        прийти из JSON).
        """
        return self.deflection if self.has_deflection else 0.0

    def to_dict(self) -> dict[str, object]:
        """Представление для журнала."""
        return {
            "order_no": self.order_no,
            "batch": self.batch,
            "operator": self.operator,
            "diameter": self.diameter,
            "wall_thickness": self.wall_thickness,
            "material": self.material,
            "length": self.length,
            "operation": self.operation,
            "has_deflection": self.has_deflection,
            "deflection": self.deflection,
            "required_straightness": self.required_straightness,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "Pipe":
        """Создаёт трубу из словаря (демо-заказы из JSON).

        Принимает и ключ ``wall``, и ``wall_thickness`` — так формат
        демо-данных устойчив к обоим вариантам.
        """
        wall = data.get("wall_thickness", data.get("wall", 0.0))
        return cls(
            order_no=str(data.get("order_no", "")),
            batch=str(data.get("batch", "")),
            operator=str(data.get("operator", "")),
            diameter=float(data.get("diameter", 0.0) or 0.0),
            wall_thickness=float(wall or 0.0),
            material=str(data.get("material", "")),
            length=float(data.get("length", 0.0) or 0.0),
            operation=str(data.get("operation", "")),
            has_deflection=bool(data.get("has_deflection", False)),
            deflection=float(data.get("deflection", 0.0) or 0.0),
            required_straightness=float(
                data.get("required_straightness", 1.5) or 1.5
            ),
        )