"""Диалоги приложения: обоснование, ручная коррекция, ошибка наладчика."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.core.explanations import build_breakdown_lines
from app.models.machine import MachineConfig
from app.models.pipe import Pipe
from app.models.result import CalculationResult
from app.services.report_service import estimate_operator_mistake
from app.utils.formatting import (
    format_m_per_min,
    format_minutes,
    format_mm,
    format_mm_per_m,
    format_percent_text,
)

#: Заголовок модальных окон приложения.
DIALOG_TITLE = "ТрубоНастрой"


class ExplanationDialog(QDialog):
    """Показывает человекочитаемое обоснование расчёта.

    Ключевая презентационная фича: директор видит, что система объяснимая,
    а не «чёрный ящик». Слева — разложение уставки, справа — текст.
    """

    def __init__(
        self,
        parent: QWidget,
        pipe: Pipe,
        result: CalculationResult,
        machine: MachineConfig,
    ) -> None:
        super().__init__(parent)
        self._pipe = pipe
        self._result = result
        self._machine = machine

        self.setWindowTitle("Обоснование расчёта")
        self.setModal(True)
        self.resize(880, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(10)

        header = QLabel(
            f"Заказ {pipe.order_no} · {pipe.designation} · {pipe.material} · "
            f"{pipe.operation}"
        )
        header.setObjectName("ValueLabel")
        layout.addWidget(header)

        columns = QHBoxLayout()
        columns.setSpacing(12)
        columns.addWidget(self._build_breakdown_box(), 5)
        columns.addWidget(self._build_text_box(), 6)
        layout.addLayout(columns, 1)

        disclaimer = QLabel(
            "Демонстрационный прототип. Расчёты модельные. "
            "Реальное управление оборудованием требует отдельной валидации."
        )
        disclaimer.setObjectName("HintLabel")
        disclaimer.setWordWrap(True)
        layout.addWidget(disclaimer)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_button = buttons.button(QDialogButtonBox.StandardButton.Close)
        close_button.setText("Закрыть")
        close_button.clicked.connect(self.accept)
        layout.addWidget(buttons)

    def _build_breakdown_box(self) -> QGroupBox:
        """Левая колонка: разложение уставки по слагаемым."""
        box = QGroupBox("Разложение уставки")
        layout = QFormLayout(box)
        layout.setSpacing(8)
        layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        for title, value in build_breakdown_lines(self._result):
            key_label = QLabel(title)
            key_label.setObjectName("FieldLabel")
            value_label = QLabel(value)
            value_label.setObjectName("ValueLabel")
            value_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            layout.addRow(key_label, value_label)
        return box

    def _build_text_box(self) -> QGroupBox:
        """Правая колонка: текст объяснения и предупреждения."""
        box = QGroupBox("Объяснение программы")
        layout = QVBoxLayout(box)
        layout.setSpacing(8)

        text = QTextBrowser()
        text.setPlainText(self._result.explanation)
        layout.addWidget(text, 1)

        if self._result.warnings:
            warnings_title = QLabel("Предупреждения:")
            warnings_title.setObjectName("FieldLabel")
            layout.addWidget(warnings_title)

            warnings_list = QListWidget()
            for message in self._result.warnings:
                warnings_list.addItem(QListWidgetItem(f"• {message}"))
            warnings_list.setMaximumHeight(150)
            layout.addWidget(warnings_list)
        return box


class ManualCorrectionDialog(QDialog):
    """Ручная коррекция уставки с обязательным указанием причины.

    Оператор может изменить уставку в пределах машины, но не может
    оставить поле причины пустым: без причины коррекция не журналируется.
    """

    def __init__(
        self,
        parent: QWidget,
        result: CalculationResult,
        machine: MachineConfig,
    ) -> None:
        super().__init__(parent)
        self._machine = machine
        self._result = result

        self.setWindowTitle("Ручная коррекция уставки")
        self.setModal(True)
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(12)

        intro = QLabel(
            f"Программа рассчитала уставку {format_mm(result.final_gap)}.\n"
            "Измените значение в пределах машины и укажите причину — "
            "коррекция попадёт в журнал переналадок."
        )
        intro.setWordWrap(True)
        intro.setObjectName("HintLabel")
        layout.addWidget(intro)

        form_box = QGroupBox("Новое значение")
        form = QFormLayout(form_box)
        form.setSpacing(10)

        self._gap_spin = QDoubleSpinBox()
        self._gap_spin.setDecimals(1)
        self._gap_spin.setSingleStep(0.1)
        self._gap_spin.setRange(machine.min_gap, machine.max_gap)
        self._gap_spin.setValue(result.final_gap)
        self._gap_spin.setSuffix(" мм")
        self._gap_spin.setToolTip(
            "Допустимый диапазон уставки машины: "
            f"{format_mm(machine.min_gap)} … {format_mm(machine.max_gap)}"
        )
        form.addRow("Итоговая уставка:", self._gap_spin)

        self._reason_edit = QLineEdit()
        self._reason_edit.setPlaceholderText(
            "Например: замер снят вручную, уставка скорректирована наладчиком"
        )
        self._reason_edit.setMaxLength(200)
        form.addRow("Причина коррекции:", self._reason_edit)

        layout.addWidget(form_box)

        self._error_label = QLabel("Укажите причину коррекции.")
        self._error_label.setStyleSheet("color: #e74c3c;")
        self._error_label.setVisible(False)
        layout.addWidget(self._error_label)

        info = QLabel(
            f"Рекомендованная скорость: {format_m_per_min(self._result.feed_speed)}. "
            f"Прогноз кривизны по расчёту: "
            f"{format_mm_per_m(self._result.predicted_residual_curvature)}."
        )
        info.setWordWrap(True)
        info.setObjectName("HintLabel")
        layout.addWidget(info)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Применить коррекцию")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> tuple[float, str]:
        """Возвращает выбранную уставку и причину коррекции."""
        return self._gap_spin.value(), self._reason_edit.text().strip()

    def _on_accept(self) -> None:
        """Проверяет наличие причины перед закрытием диалога."""
        if not self._reason_edit.text().strip():
            self._error_label.setVisible(True)
            self._reason_edit.setFocus()
            return
        self.accept()


class OperatorMistakeDialog(QDialog):
    """Показывает последствия сохранения старой уставки.

    Демонстрационный сценарий «ошибка наладчика»: сравнивается уставка,
    рассчитанная для другого диаметра, с корректной. Нужен, чтобы на
    защите показать цену ошибки переналадки в цифрах.
    """

    def __init__(
        self,
        parent: QWidget,
        result: CalculationResult,
        stale_gap: float,
        pipe: Pipe,
    ) -> None:
        super().__init__(parent)
        estimate = estimate_operator_mistake(result, stale_gap)

        self.setWindowTitle("Симуляция ошибки наладчика")
        self.setModal(True)
        self.setMinimumWidth(640)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(12)

        title = QLabel(
            f"Заказ {pipe.order_no}: труба {pipe.designation}, "
            "наладчик оставил уставку с предыдущего диаметра"
        )
        title.setObjectName("SectionTitle")
        title.setWordWrap(True)
        layout.addWidget(title)

        comparison = QGroupBox("Сравнение уставок")
        form = QFormLayout(comparison)
        form.setSpacing(8)
        stale_label = QLabel(format_mm(stale_gap))
        stale_label.setStyleSheet("color: #e74c3c; font-size: 12pt; font-weight: bold;")
        correct_label = QLabel(format_mm(result.final_gap))
        correct_label.setStyleSheet(
            "color: #2ecc71; font-size: 12pt; font-weight: bold;"
        )
        delta_label = QLabel(format_mm(estimate["delta"]))
        delta_label.setObjectName("ValueLabel")
        form.addRow("Оставленная уставка:", stale_label)
        form.addRow("Правильная уставка:", correct_label)
        form.addRow("Ошибка по величине:", delta_label)
        layout.addWidget(comparison)

        verdict = QLabel(estimate["verdict"][0].upper() + estimate["verdict"][1:] + ".")
        verdict.setWordWrap(True)
        verdict.setObjectName("FieldLabel")
        layout.addWidget(verdict)

        effects = QGroupBox("Последствия")
        effects_form = QFormLayout(effects)
        effects_form.setSpacing(8)
        severity_label = QLabel(str(estimate["severity"]).upper())
        severity_label.setObjectName("ValueLabel")
        effects_form.addRow("Уровень риска:", severity_label)
        effects_form.addRow(
            "Прогноз брака:", QLabel(format_percent_text(estimate["defect_percent"]))
        )
        effects_form.addRow(
            "Потеря времени на исправление:",
            QLabel(format_minutes(estimate["extra_time"])),
        )
        effects_form.addRow(
            "Итого на переналадку:", QLabel(format_minutes(estimate["total_time"]))
        )
        layout.addWidget(effects)

        layout.addWidget(
            QLabel(
                "Вывод: ошибка переналадки стоит нескольких часов работы "
                "и партии брака. Именно эту ошибку устраняет автоматический "
                "расчёт уставки."
            )
        )

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_button = buttons.button(QDialogButtonBox.StandardButton.Close)
        close_button.setText("Закрыть")
        close_button.clicked.connect(self.accept)
        layout.addWidget(buttons)


class DemoOrderDialog(QDialog):
    """Выбор демо-заказа для загрузки в форму."""

    def __init__(self, parent: QWidget, orders: list[Pipe]) -> None:
        super().__init__(parent)
        self._orders = orders
        self._selected_index = 0

        self.setWindowTitle("Загрузка демо-заказа")
        self.setModal(True)
        self.setMinimumWidth(620)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(12)

        intro = QLabel("Выберите заказ для демонстрации:")
        intro.setObjectName("HintLabel")
        layout.addWidget(intro)

        self._list = QListWidget()
        self._list.setMinimumHeight(170)
        for pipe in orders:
            text = (
                f"{pipe.order_no} · {pipe.designation} · {pipe.material} · "
                f"{pipe.operation}"
            )
            if pipe.has_deflection:
                text += f" · изгиб {format_mm_per_m(pipe.deflection)}"
            self._list.addItem(QListWidgetItem(text))
        self._list.setCurrentRow(0)
        self._list.currentRowChanged.connect(self._on_row_changed)
        layout.addWidget(self._list)

        self._detail = QLabel()
        self._detail.setWordWrap(True)
        self._detail.setObjectName("HintLabel")
        layout.addWidget(self._detail)
        self._on_row_changed(0)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Загрузить")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_order(self) -> Pipe | None:
        """Возвращает выбранный заказ."""
        if 0 <= self._selected_index < len(self._orders):
            return self._orders[self._selected_index]
        return None

    def _on_row_changed(self, row: int) -> None:
        """Обновляет подробности выбранного заказа."""
        if not (0 <= row < len(self._orders)):
            self._detail.setText("")
            return
        self._selected_index = row
        pipe = self._orders[row]
        deflection = (
            format_mm_per_m(pipe.deflection) if pipe.has_deflection else "не заявлен"
        )
        self._detail.setText(
            f"Партия {pipe.batch}, оператор {pipe.operator}, длина "
            f"{pipe.length:g} мм. Изгиб: {deflection}. Требуемая кривизна: "
            f"{format_mm_per_m(pipe.required_straightness)}."
        )


class PipePresetDialog(QDialog):
    """Диалог пресетов для презентации («смена диаметра 48 → 57»)."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Быстрые пресеты")
        self.setModal(True)
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(12)

        intro = QLabel(
            "Пресеты подставляют типовые ситуации участка. "
            "После выбора поля формы обновятся автоматически."
        )
        intro.setWordWrap(True)
        intro.setObjectName("HintLabel")
        layout.addWidget(intro)

        self._combo = QComboBox()
        self._combo.addItem("Смена диаметра 48 → 57 мм", "diameter_change")
        self._combo.addItem("Труба погнулась после гибки", "bent_pipe")
        layout.addWidget(self._combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Применить")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def preset_key(self) -> str:
        """Ключ выбранного пресета."""
        data = self._combo.currentData()
        return str(data) if data is not None else "diameter_change"

    def preset_title(self) -> str:
        """Название выбранного пресета для журнала сессии."""
        return self._combo.currentText()


def show_critical(parent: QWidget, title: str, text: str) -> None:
    """Показывает критическую ошибку с понятным текстом."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Critical)
    box.setWindowTitle(DIALOG_TITLE)
    box.setText(title)
    box.setInformativeText(text)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    box.exec()


def show_warning(parent: QWidget, title: str, text: str) -> None:
    """Показывает предупреждение пользователю."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(DIALOG_TITLE)
    box.setText(title)
    box.setInformativeText(text)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    box.exec()


def confirm(parent: QWidget, title: str, text: str) -> bool:
    """Запрашивает подтверждение действия."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(DIALOG_TITLE)
    box.setText(title)
    box.setInformativeText(text)
    box.setStandardButtons(
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    yes_button = box.button(QMessageBox.StandardButton.Yes)
    yes_button.setText("Применить")
    no_button = box.button(QMessageBox.StandardButton.No)
    no_button.setText("Отмена")
    return box.exec() == QMessageBox.StandardButton.Yes


class StylePreviewWidget(QWidget):
    """Небольшой вспомогательный виджет для демонстрации темы.

    Используется на вкладке «О системе», чтобы показать оформление
    элементов управления до применения настроек.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._button = QPushButton("Кнопка")
        self._button.setObjectName("PrimaryButton")
        layout.addWidget(self._button)

        self._success = QPushButton("Применить")
        self._success.setObjectName("SuccessButton")
        layout.addWidget(self._success)

        self._warning = QPushButton("Предупреждение")
        self._warning.setObjectName("DangerButton")
        layout.addWidget(self._warning)

        self._disabled = QPushButton("Недоступно")
        self._disabled.setEnabled(False)
        layout.addWidget(self._disabled)