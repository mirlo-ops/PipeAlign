"""Расчётная модель выпрямления трубы на косовалковой машине.

Ключевая функция :func:`calculate_settings` чистая: не обращается к Qt,
к диску и не зависит от состояния приложения. Все коэффициенты —
демонстрационные, подобраны так, чтобы результат выглядел правдоподобно
на защите и оставался полностью объяснимым.

Формула уставки::

    Итоговая уставка = Базовая уставка
                     + Поправка на материал
                     + Поправка на изгиб
                     + Поправка на операцию
"""

from __future__ import annotations

from typing import Any, Sequence

from app.core import validation as v
from app.core.explanations import build_explanation
from app.models.machine import MachineConfig
from app.models.pipe import Pipe
from app.models.result import (
    MANUAL_NOTE,
    RISK_HIGH,
    RISK_LOW,
    RISK_MEDIUM,
    CalculationResult,
)

#: Демо-норма времени ручной переналадки, минут.
AS_IS_TIME_MINUTES = 40.0

#: Базовая доля времени при переналадке по программе, минут.
TO_BE_BASE_MINUTES = 8.0

#: Добавка за каждый проход, минут.
TO_BE_PER_PASS_MINUTES = 2.0

#: Добавка за существенный изгиб, минут.
TO_BE_DEVIATION_EXTRA_MINUTES = 3.0

#: Добавка при ручной коррекции наладчика, минут.
TO_BE_MANUAL_EXTRA_MINUTES = 2.0

#: Демо-норма брака при ручной переналадке, %.
AS_IS_DEFECT_PERCENT = 6.0

#: Базовые пороги числа проходов по стреле прогиба, мм/м.
PASSES_LOW_DEVIATION = 4.0
PASSES_MID_DEVIATION = 10.0

#: Базовая скорость подачи и штрафы, м/мин.
BASE_FEED_SPEED = 14.0
FEED_PER_PASS = 0.7
FEED_PER_DEVIATION = 0.15
FEED_THIN_WALL_PENALTY = 1.0
FEED_HEAT_TREATMENT_PENALTY = 0.5
MIN_FEED_SPEED = 6.0

#: Коэффициент затухания изгиба за один проход.
CURVATURE_DECAY_PER_PASS = 2.5

#: Минимальный прогноз кривизны, мм/м.
MIN_PREDICTED_CURVATURE = 0.1

#: Прогноз кривизны для трубы без заявленного изгиба, мм/м.
CURVATURE_WITHOUT_DEVIATION = 0.2

#: Опорное значение диаметра для эвристической формулы, мм.
REFERENCE_DIAMETER = 2.0

#: Коэффициенты эвристической формулы базовой уставки.
HEURISTIC_CONSTANT = 1.2
HEURISTIC_WALL_FACTOR = 0.1

#: Коэффициенты подгонки по ближайшему рецепту.
RECIPE_DIAMETER_FACTOR = 0.5
RECIPE_WALL_FACTOR = 0.15

#: Порог срабатывания корректора скорости на марку стали.
DEFAULT_MATERIAL_CORRECTION = 0.0
DEFAULT_MATERIAL_SPEED_PENALTY = 0.0

#: Округление значений уставки, мм.
GAP_ROUNDING = 1

#: Баллы риска.
RISK_DEVIATION_DIVISOR = 4.0
RISK_DEVIATION_CAP = 3.0
RISK_THIN_WALL = 2.0
RISK_STAINLESS = 1.0
RISK_CLAMPED = 2.0
RISK_THREE_PASSES = 1.0
RISK_CURVATURE_ABOVE = 2.0

#: Границы уровней риска по сумме баллов.
RISK_MEDIUM_THRESHOLD = 3.0
RISK_HIGH_THRESHOLD = 6.0

#: Стрела прогиба, выше которой число проходов увеличивается при ограничении.
CLAMPED_EXTRA_PASSES_DEVIATION = 8.0

#: Шаг округления итоговых чисел.
RESULT_ROUNDING = 1


def interpolate_curve(curve: Sequence[Sequence[float]], x: float) -> float:
    """Линейная интерполяция по кривой зависимости.

    ``curve`` — последовательность пар ``[x, y]``, отсортированных по x.
    Значения ниже первой точки дают первый y, выше последней — последний y,
    поэтому кривая безопасно насыщается на краях.
    """
    if not curve:
        return 0.0
    points = [(float(px), float(py)) for px, py in curve]
    if x <= points[0][0]:
        return points[0][1]
    if x >= points[-1][0]:
        return points[-1][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= x <= x1:
            if x1 == x0:
                return y1
            share = (x - x0) / (x1 - x0)
            return y0 + share * (y1 - y0)
    return points[-1][1]  # pragma: no cover - защита от повреждённой кривой


def nearest_recipe(
    recipes: Sequence[dict[str, Any]], diameter: float
) -> dict[str, Any] | None:
    """Находит рецепт с ближайшим диаметром."""
    if not recipes:
        return None
    return min(recipes, key=lambda item: abs(float(item["diameter"]) - diameter))


def exact_recipe(
    recipes: Sequence[dict[str, Any]], diameter: float, wall: float
) -> dict[str, Any] | None:
    """Ищет рецепт с точным совпадением диаметра и толщины стенки."""
    for item in recipes:
        if (
            abs(float(item["diameter"]) - diameter) < 1e-6
            and abs(float(item["wall"]) - wall) < 1e-6
        ):
            return item
    return None


def resolve_material(materials: Sequence[dict[str, Any]], material: str) -> tuple[float, float]:
    """Возвращает ``(поправка на уставку, штраф скорости)`` для марки стали."""
    for item in materials:
        if str(item.get("id", "")) == material:
            return (
                float(item.get("correction", DEFAULT_MATERIAL_CORRECTION)),
                float(item.get("speed_penalty", DEFAULT_MATERIAL_SPEED_PENALTY)),
            )
    return DEFAULT_MATERIAL_CORRECTION, DEFAULT_MATERIAL_SPEED_PENALTY


def _base_gap(pipe: Pipe, recipes: Sequence[dict[str, Any]]) -> float:
    """Базовая уставка: рецепт, подгонка по ближайшему или эвристика."""
    exact = exact_recipe(recipes, pipe.diameter, pipe.wall_thickness)
    if exact is not None:
        return round(float(exact["gap"]), GAP_ROUNDING)

    nearest = nearest_recipe(recipes, pipe.diameter)
    if nearest is not None:
        adjusted = (
            float(nearest["gap"])
            + (pipe.diameter - float(nearest["diameter"])) * RECIPE_DIAMETER_FACTOR
            - (pipe.wall_thickness - float(nearest["wall"])) * RECIPE_WALL_FACTOR
        )
        return round(adjusted, GAP_ROUNDING)

    heuristic = (
        pipe.diameter / REFERENCE_DIAMETER
        + HEURISTIC_CONSTANT
        - pipe.wall_thickness * HEURISTIC_WALL_FACTOR
    )
    return round(heuristic, GAP_ROUNDING)


def _passes(deflection: float) -> int:
    """Число проходов по величине остаточного изгиба."""
    if deflection <= PASSES_LOW_DEVIATION:
        return 1
    if deflection <= PASSES_MID_DEVIATION:
        return 2
    return 3


def _feed_speed(
    passes: int,
    deflection: float,
    speed_penalty: float,
    wall_thickness: float,
    operation: str,
) -> float:
    """Скорость подачи с учётом проходов, изгиба, материала и стенки."""
    speed = BASE_FEED_SPEED
    speed -= FEED_PER_PASS * passes
    speed -= FEED_PER_DEVIATION * deflection
    speed -= speed_penalty
    if wall_thickness < v.THIN_WALL_THRESHOLD:
        speed -= FEED_THIN_WALL_PENALTY
    if operation == v.HEAT_TREATMENT_OPERATION:
        speed -= FEED_HEAT_TREATMENT_PENALTY
    return max(MIN_FEED_SPEED, round(speed, RESULT_ROUNDING))


def _risk_level(risk_score: float) -> str:
    """Переводит сумму баллов в текстовый уровень риска."""
    if risk_score >= RISK_HIGH_THRESHOLD:
        return RISK_HIGH
    if risk_score >= RISK_MEDIUM_THRESHOLD:
        return RISK_MEDIUM
    return RISK_LOW


def calculate_settings(
    pipe: Pipe, machine: MachineConfig, recipes: dict[str, Any]
) -> CalculationResult:
    """Рассчитывает уставку, проходы, скорость, риск и ожидаемый эффект.

    Параметр ``recipes`` — словарь из ``data/recipes.json``. Функция ничего
    не изменяет и всегда возвращает объект :class:`CalculationResult`;
    при недопустимых входных данных результат помечается ``is_valid=False``.
    """
    base_recipes = recipes.get("base_recipes", []) or []
    materials = recipes.get("materials", []) or []
    curve = recipes.get("deflection_curve", []) or []

    warnings: list[str] = []
    is_valid = True

    # 1. Проверка диапазона машины.
    if not machine.supports_diameter(pipe.diameter):
        warnings.append(v.WARNING_DIAMETER_OUT_OF_RANGE)
        is_valid = False

    # 2. Базовая уставка.
    base_gap = _base_gap(pipe, base_recipes)

    # 3. Поправка на материал.
    material_correction, speed_penalty = resolve_material(materials, pipe.material)
    known_material = any(str(item.get("id", "")) == pipe.material for item in materials)
    if not known_material:
        warnings.append(v.WARNING_UNKNOWN_MATERIAL)
    if v.is_stainless(pipe.material):
        warnings.append(v.WARNING_STAINLESS)

    # 4. Поправка на изгиб.
    deflection = pipe.effective_deflection
    if deflection > 0:
        deflection_correction = round(
            interpolate_curve(curve, deflection), GAP_ROUNDING
        )
    else:
        deflection_correction = 0.0
    if v.is_high_deflection(deflection):
        warnings.append(v.WARNING_HIGH_DEFLECTION)

    # 5. Поправка на операцию (в версии 0.1 не меняет уставку).
    operation_correction = 0.0
    if pipe.operation == v.HEAT_TREATMENT_OPERATION:
        warnings.append(v.WARNING_HEAT_TREATMENT)
    if pipe.operation == v.BENDING_OPERATION and deflection > 0:
        warnings.append(v.WARNING_BENDING_DEFLECTION)

    # 6. Итоговая уставка с ограничением по диапазону машины.
    raw_gap = base_gap + material_correction + deflection_correction + operation_correction
    was_clamped = machine.is_gap_clamped(raw_gap)
    final_gap = round(machine.clamp_gap(raw_gap), GAP_ROUNDING)
    if was_clamped:
        warnings.append(v.WARNING_GAP_CLAMPED)

    # 7. Количество проходов.
    passes = _passes(deflection)
    if was_clamped and final_gap >= machine.max_gap and deflection > CLAMPED_EXTRA_PASSES_DEVIATION:
        if passes < 3:
            passes = 3
            warnings.append(v.WARNING_EXTRA_PASSES_FOR_CLAMP)
    thin_wall = pipe.wall_thickness < v.THIN_WALL_THRESHOLD
    if thin_wall:
        warnings.append(v.WARNING_THIN_WALL)
        if passes < 2:
            passes = 2

    # 8. Скорость подачи.
    feed_speed = _feed_speed(
        passes, deflection, speed_penalty, pipe.wall_thickness, pipe.operation
    )

    # 9. Прогноз остаточной кривизны.
    if not pipe.has_deflection:
        predicted_curvature = CURVATURE_WITHOUT_DEVIATION
    else:
        predicted_curvature = max(
            MIN_PREDICTED_CURVATURE, deflection / (passes * CURVATURE_DECAY_PER_PASS)
        )
    predicted_curvature = round(predicted_curvature, RESULT_ROUNDING)

    # 10. Уровень риска.
    risk_score = 0.0
    risk_score += min(RISK_DEVIATION_CAP, deflection / RISK_DEVIATION_DIVISOR)
    if thin_wall:
        risk_score += RISK_THIN_WALL
    if v.is_stainless(pipe.material):
        risk_score += RISK_STAINLESS
    if was_clamped:
        risk_score += RISK_CLAMPED
    if passes >= 3:
        risk_score += RISK_THREE_PASSES
    curvature_above_required = predicted_curvature > pipe.required_straightness
    if curvature_above_required:
        risk_score += RISK_CURVATURE_ABOVE
    risk_level = _risk_level(risk_score)

    # 11. Дополнительные предупреждения.
    if curvature_above_required:
        warnings.append(v.WARNING_CURVATURE_ABOVE_REQUIRED)
    if passes >= 2:
        warnings.append(v.WARNING_CONTROL_AFTER_FIRST_PASS)

    result = CalculationResult(
        base_gap=base_gap,
        material_correction=round(material_correction, GAP_ROUNDING),
        deflection_correction=deflection_correction,
        operation_correction=operation_correction,
        final_gap=final_gap,
        passes=passes,
        feed_speed=feed_speed,
        predicted_residual_curvature=predicted_curvature,
        risk_level=risk_level,
        warnings=warnings,
        explanation="",
        is_valid=is_valid,
    )

    # 12. Человекочитаемое объяснение.
    result.explanation = build_explanation(pipe, machine, result)

    # 13. Оценка эффекта (базовая, без ручной коррекции).
    _fill_effect_estimate(result, pipe, manual_override=False)
    return result


def _fill_effect_estimate(
    result: CalculationResult, pipe: Pipe, manual_override: bool
) -> None:
    """Заполняет блок «как есть / как будет» в существующем результате."""
    to_be = TO_BE_BASE_MINUTES + TO_BE_PER_PASS_MINUTES * result.passes
    if pipe.effective_deflection > PASSES_LOW_DEVIATION:
        to_be += TO_BE_DEVIATION_EXTRA_MINUTES
    if manual_override:
        to_be += TO_BE_MANUAL_EXTRA_MINUTES

    result.as_is_time_minutes = AS_IS_TIME_MINUTES
    result.to_be_time_minutes = round(to_be, RESULT_ROUNDING)
    result.time_saved_minutes = round(
        max(0.0, AS_IS_TIME_MINUTES - result.to_be_time_minutes), RESULT_ROUNDING
    )
    result.as_is_trial_runs = 4
    result.to_be_trial_runs = (
        1 if pipe.effective_deflection <= PASSES_LOW_DEVIATION else 2
    )
    result.as_is_defect_percent = AS_IS_DEFECT_PERCENT
    if result.risk_level == RISK_LOW:
        result.to_be_defect_percent = 2.0
    elif result.risk_level == RISK_MEDIUM:
        result.to_be_defect_percent = 4.0
    else:
        result.to_be_defect_percent = 8.0
    result.manual_override = manual_override


def apply_manual_correction(
    pipe: Pipe, machine: MachineConfig, recipes: dict[str, Any], final_gap: float, reason: str
) -> CalculationResult:
    """Пересчитывает результат с учётом ручной правки уставки оператором.

    Используется после диалога ручной коррекции: пересчёт сохраняет
    зависимость времени от факта коррекции и переносит её в результат.
    """
    result = calculate_settings(pipe, machine, recipes)
    clamped_gap = round(machine.clamp_gap(final_gap), GAP_ROUNDING)
    warnings = list(result.warnings)
    if MANUAL_NOTE not in warnings:
        warnings.append(MANUAL_NOTE)

    updated = result.copy(
        final_gap=clamped_gap,
        manual_override=True,
        manual_reason=reason,
        warnings=warnings,
    )
    _fill_effect_estimate(updated, pipe, manual_override=True)
    updated.explanation = build_explanation(pipe, machine, updated)
    return updated