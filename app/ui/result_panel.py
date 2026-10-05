"""Правая панель: результаты расчёта и предупреждения."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QGroupBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.core import validation as v
from app.models.machine import MachineConfig
from app.models.result import (
    RISK_HIGH,
    RISK_LOW,
    RISK_MEDIUM,
    CalculationResult,
)
from app.services.auth_service import Session
from app.utils.formatting import (
    format_m_per_min,
    format_minutes,
    format_mm,
    format_mm_per_m,
    format_percent_text,
)

#: Плейсхолдер в полях до первого расчёта.
EMPTY_PLACEHOLDER = "—"


class ResultPanel(QScrollArea):
    """Показывает разбивку уставки, прогнозы, риск и предупреждения.

    Все поля только для чтения: результат меняет расчётный модуль,
    а не оператор. Единственная редактируемая величина — ручная
    коррекция, и она делается через отдельный диалог с фиксацией причины.
    """

    explanationRequested = Signal()

    def __init__(
        self,
        machine: MachineConfig,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._machine = machine

        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        layout.addWidget(self._build_gap_box())
        layout.addWidget(self._build_process_box())
        self._effect_box = self._build_effect_box()
        layout.addWidget(self._effect_box)
        layout.addWidget(self._build_warnings_box())
        layout.addStretch(1)

        self.setWidget(container)
        self.clear()

    # ------------------------------------------------------------------
    # Построение панели
    # ------------------------------------------------------------------

    def _build_gap_box(self) -> QGroupBox:
        """Группа «Уставка между валками» с разбивкой по поправкам."""
        box = QGroupBox("Уставка между валками")
        layout = QVBoxLayout(box)
        layout.setSpacing(8)

        form = QFormLayout()
        form.setSpacing(6)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.base_gap_field = self._read_only()
        self.material_field = self._read_only()
        self.deflection_field = self._read_only()
        self.operation_field = self._read_only()

        form.addRow(self._label("Базовая уставка"), self.base_gap_field)
        form.addRow(self._label("Поправка на материал"), self.material_field)
        form.addRow(self._label("Поправка на изгиб"), self.deflection_field)
        form.addRow(self._label("Поправка на операцию"), self.operation_field)
        layout.addLayout(form)

        layout.addWidget(self._divider())

        self.final_gap_field = self._read_only()
        self.final_gap_field.setMinimumHeight(34)
        self.final_gap_field.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.final_gap_field.setStyleSheet(
            "QLineEdit { background-color: #343b44; color: #ff8c00;"
            " border: 1px solid #ff8c00; border-radius: 4px;"
            " font-size: 15pt; font-weight: bold; }"
        )
        layout.addWidget(self._label("Итоговая уставка (уставка на ЧПУ)"))
        layout.addWidget(self.final_gap_field)

        self.risk_label = QLabel("Риск не рассчитан")
        self.risk_label.setObjectName("StatusBadge")
        self.risk_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.risk_label)

        self.explanation_button = QPushButton("Показать обоснование")
        self.explanation_button.setObjectName("PrimaryButton")
        self.explanation_button.setEnabled(False)
        self.explanation_button.setToolTip(
            "Почему получилась именно такая уставка: текстовое объяснение"
        )
        self.explanation_button.clicked.connect(self.explanationRequested.emit)
        layout.addWidget(self.explanation_button)

        return box

    def _build_process_box(self) -> QGroupBox:
        """Группа «Режим правки» с параметрами технологического процесса."""
        box = QGroupBox("Режим правки")
        form = QFormLayout(box)
        form.setSpacing(6)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.passes_field = self._read_only()
        self.speed_field = self._read_only()
        self.predicted_field = self._read_only()
        self.required_field = self._read_only()
        self.manual_field = self._read_only()

        self.passes_field.setToolTip(
            "Число проходов: 1 при изгибе до 4 мм/м, 2 до 10 мм/м, "
            "3 при изгибе свыше 10 мм/м. Тонкостенная труба — минимум 2."
        )
        self.speed_field.setToolTip(
            "Скорость подачи: базовые 14 м/мин минус поправки на проходы, "
            "изгиб и марку стали. Нижний предел 6 м/мин."
        )
        self.predicted_field.setToolTip(
            "Прогноз остаточной кривизны после правки по модели затухания"
        )

        form.addRow(self._label("Количество проходов"), self.passes_field)
        form.addRow(self._label("Скорость подачи"), self.speed_field)
        form.addRow(self._label("Прогноз кривизны"), self.predicted_field)
        form.addRow(self._label("Требуемая кривизна"), self.required_field)
        form.addRow(self._label("Ручная коррекция"), self.manual_field)

        return box

    def _build_effect_box(self) -> QGroupBox:
        """Группа «Ожидаемый эффект»: время, прогоны, брак.

        Группа скрывается для оператора станка: экономия переналадки
        интересует не того, кто подбирает уставку, а того, кто оценивает
        эффект проекта. Поля остаются в панели, чтобы общий код вывода
        результата не различался для обеих ролей.
        """
        box = QGroupBox("Ожидаемый эффект")
        layout = QVBoxLayout(box)
        layout.setSpacing(6)

        form = QFormLayout()
        form.setSpacing(6)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.as_is_time_field = self._read_only()
        self.to_be_time_field = self._read_only()
        self.saved_time_field = self._read_only()
        self.saved_time_field.setStyleSheet(
            "QLineEdit { color: #2ecc71; font-weight: bold; }"
        )
        self.trials_field = self._read_only()
        self.defect_field = self._read_only()

        form.addRow(self._label("Время ручной переналадки"), self.as_is_time_field)
        form.addRow(self._label("Время с программой"), self.to_be_time_field)
        form.addRow(self._label("Экономия времени"), self.saved_time_field)
        form.addRow(self._label("Пробные прогоны до / после"), self.trials_field)
        form.addRow(self._label("Прогноз брака до / после"), self.defect_field)
        layout.addLayout(form)

        note = QLabel(
            "Значения «как есть» — фиксированные демо-допущения проекта, "
            "«как будет» — расчёт программы."
        )
        note.setObjectName("HintLabel")
        note.setWordWrap(True)
        layout.addWidget(note)

        return box

    def _build_warnings_box(self) -> QGroupBox:
        """Группа предупреждений расчёта."""
        box = QGroupBox("Предупреждения")
        layout = QVBoxLayout(box)
        layout.setSpacing(6)

        self.warnings_list = QListWidget()
        self.warnings_list.setMinimumHeight(110)
        self.warnings_list.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        self.warnings_list.setWordWrap(True)
        layout.addWidget(self.warnings_list)

        self.no_warnings_label = QLabel("Предупреждений нет.")
        self.no_warnings_label.setObjectName("HintLabel")
        self.no_warnings_label.setVisible(False)
        layout.addWidget(self.no_warnings_label)

        return box

    # ------------------------------------------------------------------
    # Вспомогательные методы построения
    # ------------------------------------------------------------------

    @staticmethod
    def _label(text: str) -> QLabel:
        """Подпись поля результата."""
        label = QLabel(text)
        label.setObjectName("FieldLabel")
        return label

    @staticmethod
    def _read_only() -> QLineEdit:
        """Поле результата только для чтения."""
        field = QLineEdit()
        field.setReadOnly(True)
        field.setText(EMPTY_PLACEHOLDER)
        field.setAlignment(Qt.AlignmentFlag.AlignLeft)
        return field

    @staticmethod
    def _divider() -> QFrame:
        """Тонкий разделитель между секциями."""
        line = QFrame()
        line.setObjectName("Divider")
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFixedHeight(1)
        return line

    # ------------------------------------------------------------------
    # Отображение результата
    # ------------------------------------------------------------------

    def apply_role(self, session: Session) -> None:
        """Настраивает панель под роль сотрудника.

        Оператору скрывается «Ожидаемый эффект»: это метрики для оценки
        проекта, а не для переналадки конкретной трубы.
        """
        self._effect_box.setVisible(session.show_effect_panel)

    def set_explanation_enabled(self, enabled: bool) -> None:
        """Управляет доступностью кнопки «Показать обоснование»."""
        self.explanation_button.setEnabled(enabled)

    def clear(self) -> None:
        """Сбрасывает панель в состояние «расчёта ещё не было»."""
        for field in self._all_fields():
            field.setText(EMPTY_PLACEHOLDER)
        self.risk_label.setText("Риск не рассчитан")
        self.risk_label.setObjectName("StatusBadge")
        self._restyle_risk_label()
        self.warnings_list.clear()
        # До первого расчёта показываем подсказку, а не пустую рамку:
        # иначе панель занимает место впустую и выглядит сломанной.
        self._show_empty_warnings()
        self.explanation_button.setEnabled(False)

    def _show_empty_warnings(self) -> None:
        """Показывает состояние «расчёта ещё не было» в блоке предупреждений."""
        self.warnings_list.setVisible(False)
        self.no_warnings_label.setText(
            "Предупреждения появятся после расчёта настройки."
        )
        self.no_warnings_label.setVisible(True)

    def _all_fields(self) -> tuple[QLineEdit, ...]:
        """Все поля результата — для массового сброса."""
        return (
            self.base_gap_field,
            self.material_field,
            self.deflection_field,
            self.operation_field,
            self.final_gap_field,
            self.passes_field,
            self.speed_field,
            self.predicted_field,
            self.required_field,
            self.manual_field,
            self.as_is_time_field,
            self.to_be_time_field,
            self.saved_time_field,
            self.trials_field,
            self.defect_field,
        )

    def show_result(
        self,
        result: CalculationResult,
        required_straightness: float,
    ) -> None:
        """Выводит результат расчёта."""
        self.base_gap_field.setText(format_mm(result.base_gap))
        self.material_field.setText(
            _signed_mm(result.material_correction)
        )
        self.deflection_field.setText(
            _signed_mm(result.deflection_correction)
        )
        self.operation_field.setText(_signed_mm(result.operation_correction))
        self.final_gap_field.setText(format_mm(result.final_gap))

        self.passes_field.setText(_passes_text(result.passes))
        self.speed_field.setText(format_m_per_min(result.feed_speed))
        self.predicted_field.setText(
            format_mm_per_m(result.predicted_residual_curvature)
        )
        self.required_field.setText(format_mm_per_m(required_straightness))
        self.manual_field.setText(
            f"да — {format_mm(result.final_gap)}" if result.manual_override else "нет"
        )

        self.as_is_time_field.setText(format_minutes(result.as_is_time_minutes))
        self.to_be_time_field.setText(format_minutes(result.to_be_time_minutes))
        self.saved_time_field.setText(
            f"−{format_minutes(result.time_saved_minutes)}"
        )
        self.trials_field.setText(
            f"{result.as_is_trial_runs} / {result.to_be_trial_runs}"
        )
        self.defect_field.setText(
            f"{format_percent_text(result.as_is_defect_percent)} / "
            f"{format_percent_text(result.to_be_defect_percent)}"
        )

        self._show_risk(result.risk_level)
        self._show_warnings(result.warnings)
        self.explanation_button.setEnabled(True)

    def _show_risk(self, risk_level: str) -> None:
        """Показывает цветной индикатор уровня риска."""
        if risk_level == RISK_LOW:
            self.risk_label.setObjectName("RiskLow")
            self.risk_label.setText(f"Уровень риска: {RISK_LOW}")
        elif risk_level == RISK_MEDIUM:
            self.risk_label.setObjectName("RiskMedium")
            self.risk_label.setText(f"Уровень риска: {RISK_MEDIUM}")
        else:
            self.risk_label.setObjectName("RiskHigh")
            self.risk_label.setText(f"Уровень риска: {RISK_HIGH}")
        self._restyle_risk_label()

    def _restyle_risk_label(self) -> None:
        """Применяет стили индикатора после смены objectName."""
        self.risk_label.style().unpolish(self.risk_label)
        self.risk_label.style().polish(self.risk_label)

    def _show_warnings(self, warnings: list[str]) -> None:
        """Выводит список предупреждений с цветовой индикацией."""
        self.warnings_list.clear()
        for message in warnings:
            item = QListWidgetItem(f"⚠ {message}")
            if v.is_critical_warning(message):
                item.setForeground(Qt.GlobalColor.red)
                item.setToolTip("Требуется подтверждение оператора перед применением.")
            else:
                item.setForeground(Qt.GlobalColor.yellow)
            self.warnings_list.addItem(item)
        has_warnings = bool(warnings)
        self.warnings_list.setVisible(has_warnings)
        self.no_warnings_label.setVisible(not has_warnings)
        self.no_warnings_label.setText(
            "Предупреждений нет: параметры в норме, расчёт можно применять."
        )


def _signed_mm(value: float) -> str:
    """Поправка со знаком: ``+0,3 мм``."""
    if value > 0:
        return f"+{format_mm(value)}"
    if value < 0:
        return f"−{format_mm(abs(value))}"
    return format_mm(0.0)


def _passes_text(passes: int) -> str:
    """Число проходов со склонением слова."""
    if passes % 10 == 1 and passes % 100 != 11:
        word = "проход"
    elif 2 <= passes % 10 <= 4 and not 12 <= passes % 100 <= 14:
        word = "прохода"
    else:
        word = "проходов"
    return f"{passes} {word}"