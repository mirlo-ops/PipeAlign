"""Построение человекочитаемого объяснения расчёта.

Ключевое требование проекта: система не «чёрный ящик». Этот модуль
превращает числа в связный текст на русском языке, который наладчик
может прочитать вслух коллеге.
"""

from __future__ import annotations

from app.models.machine import MachineConfig
from app.models.pipe import Pipe
from app.models.result import CalculationResult


def format_signed(value: float) -> str:
    """Число со знаком: ``+0.3`` / ``−0.3`` / ``0.0``.

    Используется математический минус, чтобы строка выглядела в отчёте
    как формула, а не как дефис.
    """
    if value > 0:
        return f"+{value:.1f}"
    if value < 0:
        return f"−{abs(value):.1f}"
    return "0.0"


def _plause(passes: int) -> str:
    """Согласование слова «проход» по числу."""
    if passes % 10 == 1 and passes % 100 != 11:
        return "проход"
    if 2 <= passes % 10 <= 4 and not 12 <= passes % 100 <= 14:
        return "прохода"
    return "проходов"


def build_explanation(
    pipe: Pipe, machine: MachineConfig, result: CalculationResult
) -> str:
    """Собирает текстовое обоснование расчёта.

    Структура повторяет формулу уставки, поэтому текст можно читать
    как пошаговый разбор: что взяли, что добавили, что получилось.
    """
    lines: list[str] = []

    lines.append(
        f"Программа выбрала базовую уставку {result.base_gap:.1f} мм "
        f"для трубы {pipe.designation}."
    )

    if result.material_correction != 0:
        lines.append(
            f"Для материала {pipe.material} добавлена поправка "
            f"{format_signed(result.material_correction)} мм."
        )
    else:
        lines.append(
            f"Для материала {pipe.material} поправка на уставку не требуется."
        )

    if pipe.has_deflection and pipe.effective_deflection > 0:
        lines.append(
            f"Обнаружен остаточный изгиб {pipe.effective_deflection:g} мм/м, "
            f"добавлена компенсация {format_signed(result.deflection_correction)} мм."
        )
    else:
        lines.append("Остаточный изгиб не заявлен, компенсация не применялась.")

    if result.operation_correction != 0:
        lines.append(
            f"Поправка на операцию «{pipe.operation}» составила "
            f"{format_signed(result.operation_correction)} мм."
        )
    else:
        lines.append(
            f"Операция «{pipe.operation}» в версии 0.1 не изменяет числовую уставку."
        )

    if machine.is_gap_clamped(result.final_gap):
        lines.append(
            f"Итоговая уставка ограничена рабочим диапазоном машины "
            f"{machine.min_gap:g}–{machine.max_gap:g} мм."
        )
    lines.append(f"Итоговая уставка составляет {result.final_gap:.1f} мм.")
    lines.append(
        f"Рекомендуется {result.passes} {_plause(result.passes)} "
        f"со скоростью {result.feed_speed:.1f} м/мин."
    )

    verdict = "не более" if result.predicted_residual_curvature <= pipe.required_straightness else "с превышением"
    lines.append(
        f"Прогноз остаточной кривизны: {result.predicted_residual_curvature:.1f} мм/м "
        f"при требовании {verdict} {pipe.required_straightness:.1f} мм/м."
    )
    lines.append(f"Риск: {result.risk_level}.")

    if result.manual_override:
        lines.append(
            "Уставка скорректирована вручную оператором: "
            f"{result.final_gap:.1f} мм. Причина: {result.manual_reason}"
        )

    return "\n".join(lines)


def build_formula_lines() -> list[str]:
    """Формула уставки по строкам — для диалогов и отчётов."""
    return [
        "Итоговая уставка = Базовая уставка",
        "                 + Поправка на материал",
        "                 + Поправка на изгиб",
        "                 + Поправка на операцию",
    ]


def build_formula_text() -> str:
    """Формула уставки для вкладки «О системе»."""
    return "\n".join(build_formula_lines())


def build_breakdown_lines(result: CalculationResult) -> list[tuple[str, str]]:
    """Разложение уставки по строкам для диалога обоснования."""
    return [
        ("Базовая уставка (рецепт)", f"{result.base_gap:.1f} мм"),
        ("Поправка на материал", f"{format_signed(result.material_correction)} мм"),
        ("Поправка на изгиб", f"{format_signed(result.deflection_correction)} мм"),
        ("Поправка на операцию", f"{format_signed(result.operation_correction)} мм"),
        ("Итоговая уставка", f"{result.final_gap:.1f} мм"),
        ("Проходы", f"{result.passes} {_plause(result.passes)}"),
        ("Скорость подачи", f"{result.feed_speed:.1f} м/мин"),
        (
            "Прогноз кривизны",
            f"{result.predicted_residual_curvature:.1f} мм/м",
        ),
        ("Уровень риска", result.risk_level),
    ]