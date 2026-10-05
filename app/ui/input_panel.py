"""Левая панель: форма ввода параметров трубы и кнопки управления."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.models.machine import MachineConfig
from app.models.pipe import Pipe
from app.services.auth_service import Session

#: Начальные значения формы (совпадают с демо-заказом ДЕМО-002).
DEFAULT_ORDER_NO = "ДЕМО-002"
DEFAULT_BATCH = "B-204"
DEFAULT_OPERATOR = "Петров П.П."

#: Подсказки с формулами — обязательный элемент «объяснимости».
TOOLTIP_BASE_GAP = (
    "Базовая уставка берётся из справочника рецептов по диаметру и стенке.\n"
    "Если точного совпадения нет, применяется ближайший рецепт с коррекцией:\n"
    "gap = gap_рецепта + (D − D_рецепта) × 0.5 − (S − S_рецепта) × 0.15"
)
TOOLTIP_MATERIAL = (
    "Поправка на марку стали зависит от упрочняемости и склонности к наклёпу.\n"
    "Чем прочнее сталь, тем больше зазор и ниже скорость подачи."
)
TOOLTIP_DEFLECTION = (
    "Поправка на изгиб берётся линейной интерполяцией по кривой:\n"
    "изгиб 0 мм/м → 0.0 мм, 6 мм/м → 0.6 мм, 12 мм/м → 1.5 мм, 30 мм/м → 4.0 мм"
)
TOOLTIP_STRAIGHTNESS = (
    "Требование к остаточной кривизне после правки, мм/м.\n"
    "Если прогноз выше требования, риск повышается."
)
TOOLTIP_PASSES = (
    "Число проходов: 1 проход при изгибе до 4 мм/м, 2 прохода до 10 мм/м,\n"
    "3 прохода при изгибе более 10 мм/м. Тонкостенная труба — минимум 2 прохода."
)
TOOLTIP_FEED_SPEED = (
    "Скорость подачи: базовые 14 м/мин, минус 0.7 за проход, минус 0.15 за единицу\n"
    "изгиба, минус штраф марки стали. Нижний предел — 6 м/мин."
)


class InputPanel(QScrollArea):
    """Форма ввода параметров трубы.

    Виджет не содержит расчётной логики: он только собирает данные и
    сообщает о любых изменениях, чтобы главное окно могло снять
    «актуальность» ранее рассчитанного результата.
    """

    parametersChanged = Signal()
    calculateRequested = Signal()
    applyRequested = Signal()
    manualRequested = Signal()
    resetRequested = Signal()
    demoScenarioRequested = Signal()
    demoOrderRequested = Signal()
    presetRequested = Signal()
    mistakeSimulationRequested = Signal()
    explanationRequested = Signal()

    def __init__(
        self,
        machine: MachineConfig,
        materials: list[str],
        operations: list[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._machine = machine
        self._suppress_signals = False

        # ФИО сотрудника подставляется при входе и не затирается сбросом
        # формы: записи в журнале должны принадлежать вошедшему человеку.
        self._operator_name = DEFAULT_OPERATOR

        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        container = QWidget()
        self._layout = QVBoxLayout(container)
        self._layout.setContentsMargins(10, 10, 10, 10)
        self._layout.setSpacing(10)

        self._build_order_box()
        self._build_geometry_box()
        self.populate_choices(materials, operations)
        self._layout.addWidget(self._build_actions_box())
        self._preset_box = self._build_preset_box()
        self._layout.addWidget(self._preset_box)
        self._layout.addStretch(1)

        self.setWidget(container)
        self.reset()

    # ------------------------------------------------------------------
    # Построение формы
    # ------------------------------------------------------------------

    def _build_order_box(self) -> None:
        """Группа «Заказ и операция».

        Оператору станка группа не нужна: он вводит геометрию трубы, а
        номер заказа и партия приходят с нарядом. Группа скрывается, но
        остаётся в форме и сохраняет значения, поэтому расчёт и журнал
        работают одинаково для обеих ролей.
        """
        box = QGroupBox("Заказ и операция")
        form = QFormLayout(box)
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.order_edit = QLineEdit(DEFAULT_ORDER_NO)
        self.order_edit.setToolTip("Номер заказа или наряда")
        form.addRow(self._field_label("Номер заказа"), self.order_edit)

        self.batch_edit = QLineEdit(DEFAULT_BATCH)
        self.batch_edit.setToolTip("Обозначение партии труб")
        form.addRow(self._field_label("Партия"), self.batch_edit)

        self.operator_edit = QLineEdit(DEFAULT_OPERATOR)
        self.operator_edit.setToolTip("Фамилия и инициалы наладчика")
        form.addRow(self._field_label("Оператор"), self.operator_edit)

        self.material_combo = QComboBox()
        self.material_combo.setToolTip(TOOLTIP_MATERIAL)
        form.addRow(self._field_label("Марка стали"), self.material_combo)

        self.operation_combo = QComboBox()
        self.operation_combo.setToolTip(
            "Технологическая операция, после которой поступила труба"
        )
        form.addRow(self._field_label("Операция"), self.operation_combo)

        self._order_box = box
        self._layout.addWidget(box)

    def _build_geometry_box(self) -> None:
        """Группа «Геометрия трубы и изгиб»."""
        box = QGroupBox("Геометрия трубы и изгиб")
        form = QFormLayout(box)
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.diameter_spin = QDoubleSpinBox()
        self.diameter_spin.setDecimals(1)
        self.diameter_spin.setRange(self._machine.min_diameter, self._machine.max_diameter)
        self.diameter_spin.setValue(57.0)
        self.diameter_spin.setSingleStep(1.0)
        self.diameter_spin.setSuffix(" мм")
        self.diameter_spin.setToolTip(
            f"Рабочий диапазон машины: {self._machine.min_diameter:g}–"
            f"{self._machine.max_diameter:g} мм"
        )
        form.addRow(self._field_label("Диаметр трубы"), self.diameter_spin)

        self.wall_spin = QDoubleSpinBox()
        self.wall_spin.setDecimals(1)
        self.wall_spin.setRange(1.0, 8.0)
        self.wall_spin.setValue(3.5)
        self.wall_spin.setSingleStep(0.5)
        self.wall_spin.setSuffix(" мм")
        self.wall_spin.setToolTip(
            "Толщина стенки. Значения меньше 1,5 мм считаются тонкостенными:\n"
            "добавляется проход, снижается скорость, растёт риск."
        )
        form.addRow(self._field_label("Толщина стенки"), self.wall_spin)

        self.length_spin = QSpinBox()
        self.length_spin.setRange(1000, 12000)
        self.length_spin.setSingleStep(500)
        self.length_spin.setValue(6000)
        self.length_spin.setSuffix(" мм")
        self.length_spin.setToolTip("Длина трубы в заготовке")
        form.addRow(self._field_label("Длина трубы"), self.length_spin)

        self.deflection_check = QCheckBox("Есть изгиб после техпроцесса")
        self.deflection_check.setChecked(True)
        self.deflection_check.toggled.connect(self._on_deflection_toggled)
        form.addRow(self._field_label("Изгиб"), self.deflection_check)

        self.deflection_spin = QDoubleSpinBox()
        self.deflection_spin.setDecimals(1)
        self.deflection_spin.setRange(0.0, 30.0)
        self.deflection_spin.setValue(6.0)
        self.deflection_spin.setSingleStep(0.5)
        self.deflection_spin.setSuffix(" мм/м")
        self.deflection_spin.setToolTip(TOOLTIP_DEFLECTION)
        form.addRow(self._field_label("Стрела прогиба"), self.deflection_spin)

        self.straightness_spin = QDoubleSpinBox()
        self.straightness_spin.setDecimals(1)
        self.straightness_spin.setRange(0.1, 5.0)
        self.straightness_spin.setValue(1.5)
        self.straightness_spin.setSingleStep(0.1)
        self.straightness_spin.setSuffix(" мм/м")
        self.straightness_spin.setToolTip(TOOLTIP_STRAIGHTNESS)
        form.addRow(self._field_label("Требуемая кривизна"), self.straightness_spin)

        self._layout.addWidget(box)

    def _build_actions_box(self) -> QWidget:
        """Основные кнопки управления расчётом."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.calculate_button = QPushButton("Рассчитать настройку")
        self.calculate_button.setObjectName("PrimaryButton")
        self.calculate_button.setMinimumHeight(42)
        self.calculate_button.setToolTip(
            "Рассчитать уставку по формуле:\n"
            "Базовая + Материал + Изгиб + Операция"
        )
        self.calculate_button.clicked.connect(self._on_calculate_clicked)
        layout.addWidget(self.calculate_button)

        self.apply_button = QPushButton("Применить настройку")
        self.apply_button.setObjectName("SuccessButton")
        self.apply_button.setMinimumHeight(42)
        self.apply_button.setEnabled(False)
        self.apply_button.setToolTip(
            "Зафиксировать настройку в журнале переналадок.\n"
            "Доступна только после расчёта без изменений параметров."
        )
        self.apply_button.clicked.connect(self._on_apply_clicked)
        layout.addWidget(self.apply_button)

        row = QHBoxLayout()
        row.setSpacing(8)

        self.manual_button = QPushButton("Ручная коррекция")
        self.manual_button.setEnabled(False)
        self.manual_button.setToolTip(
            "Изменить рассчитанную уставку вручную.\n"
            "Причина коррекции обязательна и попадает в журнал."
        )
        self.manual_button.clicked.connect(self._on_manual_clicked)
        row.addWidget(self.manual_button)

        self.reset_button = QPushButton("Сбросить")
        self.reset_button.setToolTip("Вернуть исходные значения формы")
        self.reset_button.clicked.connect(self._on_reset_clicked)
        row.addWidget(self.reset_button)

        layout.addLayout(row)

        # Кнопки «Показать обоснование» здесь нет намеренно: обоснование
        # открывается из панели результата, рядом с самим расчётом.
        # Две одинаковые кнопки в двух панелях только перегружали форму.
        return container

    def _build_preset_box(self) -> QWidget:
        """Демонстрационные кнопки и пресеты."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.demo_order_button = QPushButton("Загрузить демо-заказ")
        self.demo_order_button.setToolTip(
            "Выбрать один из демонстрационных заказов из recipes.json"
        )
        self.demo_order_button.clicked.connect(self._on_demo_order_clicked)
        layout.addWidget(self.demo_order_button)

        self.demo_scenario_button = QPushButton("Демо-сценарий")
        self.demo_scenario_button.setObjectName("PrimaryButton")
        self.demo_scenario_button.setToolTip(
            "Автоматически проиграть презентационный сценарий:\n"
            "смена диаметра 48 → 57, появление изгиба, расчёт, применение."
        )
        self.demo_scenario_button.clicked.connect(self._on_demo_scenario_clicked)
        layout.addWidget(self.demo_scenario_button)

        self.preset_button = QPushButton("Быстрые пресеты")
        self.preset_button.setToolTip(
            "Типовые ситуации: смена диаметра, погнутая после гибки труба"
        )
        self.preset_button.clicked.connect(self._on_preset_clicked)
        layout.addWidget(self.preset_button)

        self.mistake_button = QPushButton("Симулировать ошибку наладчика")
        self.mistake_button.setToolTip(
            "Показать, к чему приводит сохранение старой уставки"
        )
        self.mistake_button.clicked.connect(self._on_mistake_clicked)
        layout.addWidget(self.mistake_button)

        return container

    @staticmethod
    def _field_label(text: str) -> QLabel:
        """Подпись поля формы."""
        label = QLabel(text)
        label.setObjectName("FieldLabel")
        return label

    @staticmethod
    def _select_combo(combo: QComboBox, value: str) -> None:
        """Выбирает значение выпадающего списка, если оно есть."""
        index = combo.findText(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    # ------------------------------------------------------------------
    # Данные формы
    # ------------------------------------------------------------------

    def populate_choices(self, materials: list[str], operations: list[str]) -> None:
        """Заполняет выпадающие списки марок стали и операций."""
        self._suppress_signals = True
        try:
            self.material_combo.clear()
            self.material_combo.addItems(materials)
            self.operation_combo.clear()
            self.operation_combo.addItems(operations)
        finally:
            self._suppress_signals = False

    def collect(self) -> Pipe:
        """Собирает объект :class:`Pipe` из полей формы."""
        return Pipe(
            order_no=self.order_edit.text().strip(),
            batch=self.batch_edit.text().strip(),
            operator=self.operator_edit.text().strip(),
            diameter=self.diameter_spin.value(),
            wall_thickness=self.wall_spin.value(),
            material=self.material_combo.currentText(),
            length=float(self.length_spin.value()),
            operation=self.operation_combo.currentText(),
            has_deflection=self.deflection_check.isChecked(),
            deflection=self.deflection_spin.value(),
            required_straightness=self.straightness_spin.value(),
        )

    def fill_from_pipe(self, pipe: Pipe, notify: bool = False) -> None:
        """Заполняет форму данными трубы."""
        self._suppress_signals = True
        try:
            self.order_edit.setText(pipe.order_no)
            self.batch_edit.setText(pipe.batch)
            self.operator_edit.setText(pipe.operator)
            self.diameter_spin.setValue(_clamp_spin(
                self.diameter_spin, pipe.diameter
            ))
            self.wall_spin.setValue(_clamp_spin(self.wall_spin, pipe.wall_thickness))
            self._select_combo(self.material_combo, pipe.material)
            self._select_combo(self.operation_combo, pipe.operation)
            self.length_spin.setValue(int(_clamp_spin(self.length_spin, pipe.length)))
            self.deflection_check.setChecked(pipe.has_deflection)
            self.deflection_spin.setValue(
                _clamp_spin(self.deflection_spin, pipe.deflection)
            )
            self.straightness_spin.setValue(
                _clamp_spin(self.straightness_spin, pipe.required_straightness)
            )
        finally:
            self._suppress_signals = False

        self._on_deflection_toggled(self.deflection_check.isChecked())
        if notify:
            self.parametersChanged.emit()

    def apply_preset(self, key: str) -> None:
        """Применяет быстрый пресет к форме.

        Пресеты используются в демо-сценарии и на защите, поэтому
        меняют только те поля, которые относятся к ситуации.
        """
        if key == "diameter_change":
            self.diameter_spin.setValue(57.0)
            self.wall_spin.setValue(3.5)
            self._select_combo(self.material_combo, "09Г2С")
            self._select_combo(self.operation_combo, "после механообработки")
        elif key == "bent_pipe":
            self.diameter_spin.setValue(57.0)
            self.wall_spin.setValue(3.5)
            self._select_combo(self.operation_combo, "после гибки")
            self.deflection_check.setChecked(True)
            self.deflection_spin.setValue(6.0)
            self._on_deflection_toggled(True)
        self.parametersChanged.emit()

    def reset(self) -> None:
        """Возвращает форму к исходному состоянию."""
        self._suppress_signals = True
        try:
            self.order_edit.setText(DEFAULT_ORDER_NO)
            self.batch_edit.setText(DEFAULT_BATCH)
            self.operator_edit.setText(self._operator_name)
            self.diameter_spin.setValue(57.0)
            self.wall_spin.setValue(3.5)
            self.length_spin.setValue(6000)
            self._select_combo(self.material_combo, "09Г2С")
            self._select_combo(self.operation_combo, "после гибки")
            self.deflection_check.setChecked(True)
            self.deflection_spin.setValue(6.0)
            self.straightness_spin.setValue(1.5)
        finally:
            self._suppress_signals = False
        self._on_deflection_toggled(True)

    def set_deflection_enabled(self, enabled: bool) -> None:
        """Включает или выключает поле стрелы прогиба."""
        self.deflection_spin.setEnabled(enabled)

    def set_apply_enabled(self, enabled: bool) -> None:
        """Управляет доступностью кнопки «Применить настройку»."""
        self.apply_button.setEnabled(enabled)

    def set_manual_enabled(self, enabled: bool) -> None:
        """Управляет доступностью кнопки «Ручная коррекция»."""
        self.manual_button.setEnabled(enabled)

    def apply_role(self, session: Session) -> None:
        """Настраивает форму под роль сотрудника.

        Оператору скрывается группа «Заказ и операция»: её поля приходят
        с нарядом, и вводить их у станка каждый раз не нужно. Поля не
        удаляются, а только скрываются, поэтому :meth:`collect` продолжает
        отдавать полный :class:`Pipe`, а расчёт и журнал не меняются.
        """
        self._operator_name = session.operator_name
        self._order_box.setVisible(session.show_order_form)
        self.operator_edit.setText(session.operator_name)

    def set_controls_enabled(self, enabled: bool) -> None:
        """Блокирует форму на время демо-сценария."""
        self.order_edit.setEnabled(enabled)
        self.batch_edit.setEnabled(enabled)
        self.operator_edit.setEnabled(enabled)
        self.diameter_spin.setEnabled(enabled)
        self.wall_spin.setEnabled(enabled)
        self.material_combo.setEnabled(enabled)
        self.operation_combo.setEnabled(enabled)
        self.length_spin.setEnabled(enabled)
        self.straightness_spin.setEnabled(enabled)
        self.deflection_check.setEnabled(enabled)
        self.set_deflection_enabled(enabled and self.deflection_check.isChecked())
        for button in (
            self.calculate_button,
            self.apply_button,
            self.manual_button,
            self.reset_button,
            self.demo_order_button,
            self.demo_scenario_button,
            self.preset_button,
            self.mistake_button,
        ):
            button.setEnabled(enabled)

    # ------------------------------------------------------------------
    # Обработчики
    # ------------------------------------------------------------------

    def _on_deflection_toggled(self, checked: bool) -> None:
        """Включает поле прогиба только при установленном флажке."""
        self.deflection_spin.setEnabled(checked)
        if not self._suppress_signals:
            self.parametersChanged.emit()

    def _on_calculate_clicked(self) -> None:
        """Запрашивает расчёт."""
        self.calculateRequested.emit()

    def _on_apply_clicked(self) -> None:
        """Запрашивает применение настройки."""
        self.applyRequested.emit()

    def _on_manual_clicked(self) -> None:
        """Запрашивает открытие диалога ручной коррекции."""
        self.manualRequested.emit()

    def _on_reset_clicked(self) -> None:
        """Сбрасывает форму и сообщает об этом."""
        self.reset()
        self.parametersChanged.emit()

    def _on_demo_order_clicked(self) -> None:
        """Запрашивает диалог выбора демо-заказа."""
        self.demoOrderRequested.emit()

    def _on_demo_scenario_clicked(self) -> None:
        """Запрашивает запуск демо-сценария."""
        self.demoScenarioRequested.emit()

    def _on_preset_clicked(self) -> None:
        """Запрашивает диалог пресетов."""
        self.presetRequested.emit()

    def _on_mistake_clicked(self) -> None:
        """Запрашивает симуляцию ошибки наладчика."""
        self.mistakeSimulationRequested.emit()


def _clamp_spin(spin_box: QDoubleSpinBox, value: float) -> float:
    """Ограничивает значение в пределах спинбокса."""
    return max(spin_box.minimum(), min(spin_box.maximum(), float(value)))


def _select_combo(combo: QComboBox, value: str) -> None:
    """Выбирает значение в выпадающем списке, если оно есть."""
    index = combo.findText(value)
    if index >= 0:
        combo.setCurrentIndex(index)