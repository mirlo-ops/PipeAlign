"""Отчёты: метрики, сравнение «как есть / как будет» и экспорт CSV.

Формирование отчёта не зависит от Qt: его можно вызвать из консоли
или из теста. Запись файлов выполняется в кодировке ``utf-8-sig`` с
разделителем ``;``, чтобы русский Excel открывал файлы без танцев.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Sequence

from app.core.explanations import build_formula_text
from app.models.machine import MachineConfig
from app.models.pipe import Pipe
from app.models.result import CalculationResult
from app.utils.formatting import (
    format_minutes,
    format_m_per_min,
    format_mm,
    format_mm_per_m,
    format_percent_text,
)

#: Разделитель CSV для русского Excel.
CSV_DELIMITER = ";"

#: Кодировка CSV с BOM, чтобы Excel корректно распознал кириллицу.
CSV_ENCODING = "utf-8-sig"

#: Значения для показателей, которые оцениваются экспертно, а не расчётом.
#: Это демо-допущения проекта, они одинаковы для всех сравнений.
SUBJECTIVE_ROWS: tuple[tuple[str, str, str], ...] = (
    (
        "Зависимость от оператора",
        "высокая: подбор на глаз и по памяти",
        "низкая: расчёт по формальным признакам",
    ),
    (
        "Прослеживаемость настроек",
        "отсутствует: настройка нигде не фиксируется",
        "полная: расчёт и результат в журнале",
    ),
    (
        "Обучение нового оператора",
        "долгое: передача опыта на словах",
        "короткое: объяснение по каждой настройке",
    ),
)


def _risk_color_name(risk_level: str) -> str:
    """Человекочитаемое имя уровня риска для отчёта."""
    mapping = {"низкий": "низкий", "средний": "средний", "высокий": "высокий"}
    return mapping.get(risk_level, risk_level)


def comparison_rows(result: CalculationResult) -> list[tuple[str, str, str]]:
    """Строки сравнения «как есть / как будет» по результату расчёта."""
    trials_reduction = max(0, result.as_is_trial_runs - result.to_be_trial_runs)
    trials_text = (
        f"{result.as_is_trial_runs} прогона"
        if trials_reduction
        else f"{result.as_is_trial_runs} прогонов"
    )
    trials_new = (
        f"{result.to_be_trial_runs} прогон"
        if result.to_be_trial_runs == 1
        else f"{result.to_be_trial_runs} прогона"
    )
    return [
        (
            "Время переналадки",
            format_minutes(result.as_is_time_minutes),
            format_minutes(result.to_be_time_minutes),
        ),
        ("Пробные прогоны", trials_text, trials_new),
        (
            "Брак по кривизне",
            f"{format_percent_text(result.as_is_defect_percent)} "
            f"({_defect_note(result.as_is_defect_percent)})",
            f"{format_percent_text(result.to_be_defect_percent)} "
            f"({_defect_note(result.to_be_defect_percent)})",
        ),
        *SUBJECTIVE_ROWS,
    ]


def _defect_note(value: float) -> str:
    """Пояснение к проценту брака."""
    if value <= 2.5:
        return "низкий риск"
    if value <= 5.0:
        return "умеренный риск"
    return "высокий риск, требуется контроль"


def build_summary(
    result: CalculationResult,
    pipe: Pipe,
    machine: MachineConfig,
    journal_aggregates: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Собирает сводку по последнему применению для верхних карточек отчёта."""
    aggregates = journal_aggregates or {}
    trials_reduction = max(0, result.as_is_trial_runs - result.to_be_trial_runs)
    return {
        "time_saved": format_minutes(result.time_saved_minutes),
        "time_saved_value": result.time_saved_minutes,
        "as_is_time": format_minutes(result.as_is_time_minutes),
        "to_be_time": format_minutes(result.to_be_time_minutes),
        "trial_runs_reduction": f"−{trials_reduction}" if trials_reduction else "0",
        "trial_runs_as_is": str(result.as_is_trial_runs),
        "trial_runs_to_be": str(result.to_be_trial_runs),
        "defect_to_be": format_percent_text(result.to_be_defect_percent),
        "defect_as_is": format_percent_text(result.as_is_defect_percent),
        "risk": _risk_color_name(result.risk_level),
        "final_gap": format_mm(result.final_gap),
        "feed_speed": format_m_per_min(result.feed_speed),
        "passes": str(result.passes),
        "predicted_curvature": format_mm_per_m(result.predicted_residual_curvature),
        "required_curvature": format_mm_per_m(pipe.required_straightness),
        "order_no": pipe.order_no,
        "designation": pipe.designation,
        "material": pipe.material,
        "operation": pipe.operation,
        "machine": machine.name,
        "journal_total": str(int(aggregates.get("total", 0))),
        "journal_applied": str(int(aggregates.get("applied", 0))),
        "journal_saved_total": format_minutes(float(aggregates.get("saved_total", 0.0))),
        "journal_saved_average": format_minutes(float(aggregates.get("saved_average", 0.0))),
        "journal_manual": str(int(aggregates.get("manual_overrides", 0))),
        "journal_high_risk": str(int(aggregates.get("high_risk", 0))),
        "formula": build_formula_text(),
    }


def build_report_text(
    result: CalculationResult,
    pipe: Pipe,
    machine: MachineConfig,
    journal_aggregates: dict[str, float] | None = None,
) -> str:
    """Формирует текстовый отчёт для сохранения в файл."""
    summary = build_summary(result, pipe, machine, journal_aggregates)
    lines: list[str] = [
        "ТрубоНастрой — отчёт по переналадке",
        "=" * 56,
        f"Заказ: {pipe.order_no}   Партия: {pipe.batch}   Оператор: {pipe.operator}",
        f"Труба: {pipe.designation}, {pipe.material}, длина {pipe.length:g} мм",
        f"Операция: {pipe.operation}",
        f"Изгиб: {'есть, ' + format_mm_per_m(pipe.deflection) if pipe.has_deflection else 'не заявлен'}",
        f"Требуемая кривизна: {format_mm_per_m(pipe.required_straightness)}",
        "",
        f"Машина: {machine.name}",
        "",
        "РЕЗУЛЬТАТ РАСЧЁТА",
        "-" * 56,
        f"Базовая уставка: {format_mm(result.base_gap)}",
        f"Поправка на материал: {format_mm(result.material_correction)}",
        f"Поправка на изгиб: {format_mm(result.deflection_correction)}",
        f"Поправка на операцию: {format_mm(result.operation_correction)}",
        f"Итоговая уставка: {format_mm(result.final_gap)}",
        f"Проходы: {result.passes}",
        f"Скорость подачи: {format_m_per_min(result.feed_speed)}",
        f"Прогноз остаточной кривизны: {format_mm_per_m(result.predicted_residual_curvature)}",
        f"Уровень риска: {result.risk_level}",
        f"Ручная коррекция: {'да' if result.manual_override else 'нет'}",
        "",
        "СРАВНЕНИЕ «КАК ЕСТЬ / КАК БУДЕТ»",
        "-" * 56,
    ]
    for title, before, after in comparison_rows(result):
        lines.append(f"{title}: {before} → {after}")
    lines += [
        "",
        "ОБОСНОВАНИЕ",
        "-" * 56,
        result.explanation,
        "",
        "ПРЕДУПРЕЖДЕНИЯ",
        "-" * 56,
    ]
    if result.warnings:
        lines.extend(f"• {item}" for item in result.warnings)
    else:
        lines.append("Предупреждений нет.")
    lines += [
        "",
        "АГРЕГИРОВАННЫЕ ДАННЫЕ ЖУРНАЛА",
        "-" * 56,
        f"Всего записей: {summary['journal_total']}",
        f"Применённых настроек: {summary['journal_applied']}",
        f"Суммарная экономия: {summary['journal_saved_total']}",
        f"Средняя экономия: {summary['journal_saved_average']}",
        f"Ручных коррекций: {summary['journal_manual']}",
        f"Применений с высоким риском: {summary['journal_high_risk']}",
        "",
        "ФОРМУЛА",
        "-" * 56,
        build_formula_text(),
        "",
        "Демонстрационный прототип. Расчёты модельные. "
        "Реальное управление оборудованием требует отдельной валидации.",
    ]
    return "\n".join(lines)


def write_csv(path: str | Path, header: Sequence[str], rows: Sequence[Sequence[str]]) -> Path:
    """Записывает CSV в кодировке utf-8-sig с разделителем «;»."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding=CSV_ENCODING, newline="") as handle:
        writer = csv.writer(handle, delimiter=CSV_DELIMITER, lineterminator="\r\n")
        writer.writerow(list(header))
        writer.writerows([list(row) for row in rows])
    return target


def report_csv(
    path: str | Path,
    result: CalculationResult,
    pipe: Pipe,
    machine: MachineConfig,
    journal_aggregates: dict[str, float] | None = None,
) -> Path:
    """Экспортирует сводный отчёт по переналадке в CSV."""
    summary = build_summary(result, pipe, machine, journal_aggregates)
    header = ["Раздел", "Показатель", "Значение"]
    rows: list[list[str]] = [
        ["Исходные данные", "Заказ", pipe.order_no],
        ["Исходные данные", "Партия", pipe.batch],
        ["Исходные данные", "Оператор", pipe.operator],
        ["Исходные данные", "Труба", pipe.designation],
        ["Исходные данные", "Марка стали", pipe.material],
        ["Исходные данные", "Операция", pipe.operation],
        ["Исходные данные", "Требуемая кривизна", format_mm_per_m(pipe.required_straightness)],
        ["Расчёт", "Базовая уставка", format_mm(result.base_gap)],
        ["Расчёт", "Поправка на материал", format_mm(result.material_correction)],
        ["Расчёт", "Поправка на изгиб", format_mm(result.deflection_correction)],
        ["Расчёт", "Поправка на операцию", format_mm(result.operation_correction)],
        ["Расчёт", "Итоговая уставка", format_mm(result.final_gap)],
        ["Расчёт", "Проходы", str(result.passes)],
        ["Расчёт", "Скорость подачи", format_m_per_min(result.feed_speed)],
        ["Расчёт", "Прогноз кривизны", format_mm_per_m(result.predicted_residual_curvature)],
        ["Расчёт", "Уровень риска", result.risk_level],
    ]
    for title, before, after in comparison_rows(result):
        rows.append(["Сравнение как есть / как будет", title, f"{before} → {after}"])
    rows += [
        ["Журнал", "Всего записей", summary["journal_total"]],
        ["Журнал", "Суммарная экономия", summary["journal_saved_total"]],
        ["Журнал", "Средняя экономия", summary["journal_saved_average"]],
        ["Журнал", "Ручных коррекций", summary["journal_manual"]],
        ["Журнал", "Применений с высоким риском", summary["journal_high_risk"]],
        ["Обоснование", "Текст расчёта", result.explanation.replace("\n", " ")],
        [
            "Ограничение",
            "Дисклеймер",
            "Демонстрационный прототип. Расчёты модельные. "
            "Реальное управление оборудованием требует отдельной валидации.",
        ],
    ]
    return write_csv(path, header, rows)


def estimate_operator_mistake(result: CalculationResult, stale_gap: float) -> dict[str, Any]:
    """Оценивает последствия сохранения старой уставки.

    Используется кнопкой «Симулировать ошибку наладчика»: показывает,
    чем обернулась бы настройка, рассчитанная для другого диаметра.
    """
    delta = result.final_gap - stale_gap
    if abs(delta) < 0.05:
        verdict = "уставка практически совпадает, риск низкий"
        defect = result.to_be_defect_percent
        extra_time = 0.0
        severity = "низкий"
    elif delta > 0:
        verdict = (
            "зазор меньше требуемого: труба будет проходить с избыточным "
            "наклоном, риск завала валков и брака по геометрии"
        )
        defect = min(100.0, result.as_is_defect_percent + abs(delta) * 4.0)
        extra_time = 20.0
        severity = "высокий" if abs(delta) > 5 else "средний"
    else:
        verdict = (
            "зазор больше требуемого: труба будет проходить с недостаточным "
            "наклоном, остаточная кривизна выйдет за допуск"
        )
        defect = min(100.0, result.as_is_defect_percent + abs(delta) * 3.0)
        extra_time = 25.0
        severity = "высокий" if abs(delta) > 5 else "средний"
    defect = round(defect, 1)
    total_time = round(
        result.as_is_time_minutes + extra_time + result.to_be_time_minutes, 1
    )
    return {
        "stale_gap": stale_gap,
        "delta": round(delta, 1),
        "verdict": verdict,
        "defect_percent": defect,
        "extra_time": extra_time,
        "total_time": total_time,
        "severity": severity,
    }


def write_text(path: str | Path, text: str) -> Path:
    """Записывает текстовый отчёт в UTF-8."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target