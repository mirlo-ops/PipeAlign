"""Результат расчёта уставки и оценка ожидаемого эффекта."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

#: Уровни риска, используются в UI, журнале и отчётах.
RISK_LOW = "низкий"
RISK_MEDIUM = "средний"
RISK_HIGH = "высокий"

RISK_ORDER: tuple[str, ...] = (RISK_LOW, RISK_MEDIUM, RISK_HIGH)

#: Подпись ручной коррекции, попадающая в предупреждения.
MANUAL_NOTE = "Настройка изменена вручную оператором."


@dataclass(slots=True)
class CalculationResult:
    """Полный результат расчёта для одной трубы.

    Разбивка уставки хранится отдельно от итога, чтобы интерфейс мог
    показать ход решения по шагам, а директор — увидеть обоснование.
    """

    base_gap: float
    material_correction: float
    deflection_correction: float
    operation_correction: float
    final_gap: float
    passes: int
    feed_speed: float
    predicted_residual_curvature: float
    risk_level: str
    warnings: list[str] = field(default_factory=list)
    explanation: str = ""
    as_is_time_minutes: float = 0.0
    to_be_time_minutes: float = 0.0
    time_saved_minutes: float = 0.0
    as_is_trial_runs: int = 0
    to_be_trial_runs: int = 0
    as_is_defect_percent: float = 0.0
    to_be_defect_percent: float = 0.0
    is_valid: bool = True
    manual_override: bool = False
    manual_reason: str = ""

    @property
    def total_correction(self) -> float:
        """Сумма всех поправок (итог минус базовая уставка)."""
        return (
            self.material_correction
            + self.deflection_correction
            + self.operation_correction
        )

    @property
    def is_high_risk(self) -> bool:
        """Требуется ли дополнительное подтверждение перед применением."""
        return self.risk_level == RISK_HIGH

    def copy(self, **changes: object) -> "CalculationResult":
        """Копия результата с применёнными изменениями."""
        return replace(self, **changes)  # type: ignore[arg-type]

    def to_dict(self) -> dict[str, object]:
        """Плоское представление результата (используется в отчётах)."""
        return {
            "base_gap": self.base_gap,
            "material_correction": self.material_correction,
            "deflection_correction": self.deflection_correction,
            "operation_correction": self.operation_correction,
            "final_gap": self.final_gap,
            "passes": self.passes,
            "feed_speed": self.feed_speed,
            "predicted_residual_curvature": self.predicted_residual_curvature,
            "risk_level": self.risk_level,
            "warnings": list(self.warnings),
            "explanation": self.explanation,
            "as_is_time_minutes": self.as_is_time_minutes,
            "to_be_time_minutes": self.to_be_time_minutes,
            "time_saved_minutes": self.time_saved_minutes,
            "as_is_trial_runs": self.as_is_trial_runs,
            "to_be_trial_runs": self.to_be_trial_runs,
            "as_is_defect_percent": self.as_is_defect_percent,
            "to_be_defect_percent": self.to_be_defect_percent,
            "is_valid": self.is_valid,
            "manual_override": self.manual_override,
            "manual_reason": self.manual_reason,
        }