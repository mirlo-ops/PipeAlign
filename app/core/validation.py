"""Проверка входных данных расчёта.

Модуль не зависит от Qt: расчётный слой можно тестировать и запускать
в консоли. Здесь же собраны тексты предупреждений, чтобы формулировки
в UI и в отчётах совпадали.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.machine import MachineConfig
from app.models.pipe import Pipe

#: Минимальная толщина стенки, ниже которой труба считается тонкостенной.
THIN_WALL_THRESHOLD = 1.5

#: Стрела прогиба, выше которой изгиб считается высоким.
HIGH_DEFLECTION_THRESHOLD = 10.0

#: Марки сталей, для которых в модели учтён повышенный риск.
STAINLESS_MARKERS: tuple[str, ...] = ("12Х18Н10Т", "40Х13", "30ХМА")

#: Операция, после которой возможно повышение жёсткости.
HEAT_TREATMENT_OPERATION = "после термообработки"

#: Операция, связанная с остаточным изгибом.
BENDING_OPERATION = "после гибки"

WARNING_DIAMETER_OUT_OF_RANGE = (
    "Диаметр трубы вне рабочего диапазона машины, настройку применить нельзя."
)
WARNING_UNKNOWN_MATERIAL = (
    "Марка стали отсутствует в справочнике, поправка на материал не применена."
)
WARNING_THIN_WALL = (
    "Тонкостенная труба: рекомендуется снизить скорость и добавить контрольный проход."
)
WARNING_HIGH_DEFLECTION = (
    "Высокая стрела прогиба: может потребоваться повторная правка после первого прохода."
)
WARNING_GAP_CLAMPED = "Уставка ограничена диапазоном машины."
WARNING_CURVATURE_ABOVE_REQUIRED = (
    "Прогноз остаточной кривизны выше требуемой, гарантия соответствия не обеспечивается."
)
WARNING_STAINLESS = (
    "Нержавеющая сталь: повышенный риск упрочнения и разнотолщинности, нужен контроль."
)
WARNING_HEAT_TREATMENT = (
    "После термообработки возможно повышение жёсткости, рекомендуется контроль после первого прохода."
)
WARNING_BENDING_DEFLECTION = (
    "Обнаружен остаточный изгиб после гибки, включена компенсация."
)
WARNING_CONTROL_AFTER_FIRST_PASS = (
    "Рекомендуется контроль геометрии после первого прохода."
)
WARNING_EXTRA_PASSES_FOR_CLAMP = (
    "Уставка ограничена, число проходов увеличено до компенсации изгиба."
)
WARNING_PREDICTED_OVER_LIMIT = (
    "Прогноз остаточной кривизны может превысить требование после всех проходов."
)

#: Подстроки предупреждений, при которых перед применением нужно
#: дополнительное подтверждение оператора.
CRITICAL_WARNING_MARKERS: tuple[str, ...] = (
    "вне рабочего диапазона",
    "выше требуемой",
    "может превысить требование",
    "уставка ограничена диапазоном",
)


@dataclass(slots=True)
class ValidationIssue:
    """Одна замечательная проблема входных данных."""

    field: str
    message: str

    def __str__(self) -> str:  # pragma: no cover - удобство отладки
        return f"{self.field}: {self.message}"


def is_thin_wall(wall_thickness: float) -> bool:
    """Тонкостенная ли труба по демо-критерию."""
    return wall_thickness < THIN_WALL_THRESHOLD


def is_high_deflection(deflection: float) -> bool:
    """Высокая ли стрела прогиба по демо-критерию."""
    return deflection > HIGH_DEFLECTION_THRESHOLD


def is_stainless(material: str) -> bool:
    """Относится ли марка к нержавеющим."""
    return any(marker in material for marker in STAINLESS_MARKERS)


def is_critical_warning(message: str) -> bool:
    """Требует ли предупреждение явного подтверждения оператора."""
    lowered = message.lower()
    return any(marker in lowered for marker in CRITICAL_WARNING_MARKERS)


def critical_warnings(messages: list[str]) -> list[str]:
    """Отбирает предупреждения, требующие подтверждения."""
    return [message for message in messages if is_critical_warning(message)]


def validate_pipe(pipe: Pipe, machine: MachineConfig) -> list[ValidationIssue]:
    """Проверяет данные трубы и возвращает список проблем.

    Пустой список означает, что расчёт можно выполнять.
    """
    issues: list[ValidationIssue] = []

    if not pipe.order_no.strip():
        issues.append(ValidationIssue("order_no", "Не указан номер заказа."))
    if not pipe.operator.strip():
        issues.append(ValidationIssue("operator", "Не указан оператор."))
    if pipe.diameter <= 0:
        issues.append(ValidationIssue("diameter", "Диаметр должен быть больше нуля."))
    elif not machine.supports_diameter(pipe.diameter):
        issues.append(
            ValidationIssue(
                "diameter",
                f"Диаметр {pipe.diameter:g} мм вне диапазона "
                f"{machine.min_diameter:g}–{machine.max_diameter:g} мм.",
            )
        )
    if pipe.wall_thickness <= 0:
        issues.append(
            ValidationIssue("wall_thickness", "Толщина стенки должна быть больше нуля.")
        )
    elif pipe.wall_thickness > pipe.diameter / 2:
        issues.append(
            ValidationIssue(
                "wall_thickness",
                "Толщина стенки не может превышать половину диаметра.",
            )
        )
    if pipe.length <= 0:
        issues.append(ValidationIssue("length", "Длина трубы должна быть больше нуля."))
    if pipe.has_deflection and pipe.deflection < 0:
        issues.append(ValidationIssue("deflection", "Стрела прогиба не может быть отрицательной."))
    if pipe.required_straightness <= 0:
        issues.append(
            ValidationIssue(
                "required_straightness", "Требуемая кривизна должна быть больше нуля."
            )
        )
    return issues


def pipe_to_text(pipe: Pipe) -> str:
    """Краткое текстовое описание трубы для логов и отчётов."""
    parts = [
        f"заказ {pipe.order_no}",
        f"партия {pipe.batch}",
        pipe.designation,
        pipe.material,
        pipe.operation,
    ]
    if pipe.has_deflection:
        parts.append(f"изгиб {pipe.deflection:g} мм/м")
    else:
        parts.append("изгиб не заявлен")
    return ", ".join(parts)