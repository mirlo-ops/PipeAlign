"""Символическая схема косовалковой правильной машины.

Виджет построен на ``QGraphicsView``/``QGraphicsScene``. Геометрия
условная: положение валков пропорционально значению уставки, а не
реальной кинематике станка. Задача схемы — показать направление
движения валков и разницу между текущей и целевой уставкой.
"""

from __future__ import annotations

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QObject,
    QPropertyAnimation,
    QRectF,
    Qt,
    Signal,
)
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QGraphicsLineItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from app.models.machine import MachineConfig
from app.utils.formatting import format_mm

#: Размеры сцены в условных единицах. Пропорции подобраны так, чтобы
#: схема читалась и при минимальной ширине окна 1280 px.
SCENE_WIDTH = 820.0
SCENE_HEIGHT = 476.0

#: Границы корпуса станка и его основания.
FRAME_LEFT = 200.0
FRAME_RIGHT = 800.0
FRAME_TOP = 60.0
FRAME_BOTTOM = 380.0
BASE_LEFT = 180.0
BASE_RIGHT = 820.0
BASE_TOP = 380.0
BASE_BOTTOM = 412.0

#: Колонка подписей слева от станка.
LABEL_COLUMN_X = 16.0
LABEL_COLUMN_WIDTH = 174.0

#: Вертикальные позиции подписей.
TITLE_Y = 22.0
ROLLER_LABEL_Y = 44.0
GAP_LABEL_Y = 214.0
STATUS_Y = 424.0
DISCLAIMER_Y = 444.0

#: Габариты валка в сцене.
ROLLER_HEIGHT = 34.0
ROLLER_WIDTH = 58.0

#: Горизонтальные координаты трёх позиций валков внутри корпуса станка.
ROLLER_POSITIONS: tuple[float, ...] = (300.0, 500.0, 700.0)

#: Высота, на которой проходит ось трубы.
PIPE_AXIS_Y = 220.0

#: Множитель «миллиметры уставки → единицы сцены».
GAP_SCALE = 2.6

#: Ширина трубы при минимальном диаметре и прибавка на каждый миллиметр.
PIPE_BASE_WIDTH = 150.0
PIPE_WIDTH_PER_MM = 4.0

#: Длительность анимации перемещения валков, мс.
ANIMATION_DURATION_MS = 850

#: Цвета состояний схемы.
COLOR_IDLE = QColor("#6b7684")
COLOR_PREVIEW = QColor("#ff8c00")
COLOR_APPLIED = QColor("#2ecc71")
COLOR_ERROR = QColor("#e74c3c")
COLOR_PIPE = QColor("#8f9aa6")
COLOR_FRAME = QColor("#3d4652")
COLOR_SECONDARY = QColor("#a0aab5")
COLOR_MUTED = QColor("#5c6672")

#: Статусы схемы.
STATUS_WAITING = "Ожидание расчёта"
STATUS_CALCULATED = "Расчёт выполнен"
STATUS_APPLIED = "Применено"
STATUS_MANUAL = "Ручная коррекция"
STATUS_ERROR = "Ошибка параметров"


class OffsetDriver(QObject):
    """Драйвер анимации смещения валков.

    ``QGraphicsItem`` не является ``QObject``, поэтому анимировать его
    свойство штатным ``QPropertyAnimation`` нельзя. Этот маленький
    QObject-держатель даёт анимируемое свойство, а валки обновляются
    обработчиком :meth:`set_offsets`.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._value = 0.0
        self._rollers: list[AnimatedRollers] = []

    def attach(self, rollers: list[AnimatedRollers]) -> None:
        """Передаёт драйверу список валков для синхронного перемещения."""
        self._rollers = rollers

    def value(self) -> float:
        """Текущее значение смещения."""
        return self._value

    def set_value(self, value: float) -> None:
        """Задаёт смещение и переносит его на все валки."""
        self._value = float(value)
        for roller in self._rollers:
            roller.set_offset(self._value)

    value_property = Property(float, value, set_value)


class AnimatedRollers(QGraphicsRectItem):
    """Валок с анимируемым вертикальным смещением.

    Смещение объявлено как Qt-property, поэтому анимируется штатным
    ``QPropertyAnimation`` без блокировки интерфейса.
    """

    def __init__(self, x: float, is_top: bool) -> None:
        super().__init__()
        self._is_top = is_top
        self._x = x
        self._offset = 0.0
        self.setPen(QPen(COLOR_FRAME, 1))
        self.setBrush(QBrush(COLOR_IDLE))
        self.setZValue(5)

    def offset(self) -> float:
        """Текущее вертикальное смещение валка."""
        return self._offset

    def set_offset(self, value: float) -> None:
        """Задаёт вертикальное смещение и обновляет геометрию."""
        self._offset = float(value)
        self._refresh()

    offset_value = Property(float, offset, set_offset)

    def _refresh(self) -> None:
        """Пересчитывает прямоугольник валка по текущему смещению."""
        center_y = (
            PIPE_AXIS_Y - self._offset if self._is_top else PIPE_AXIS_Y + self._offset
        )
        top = center_y - ROLLER_HEIGHT / 2
        self.setRect(QRectF(self._x - ROLLER_WIDTH / 2, top, ROLLER_WIDTH, ROLLER_HEIGHT))

    def apply_color(self, color: QColor) -> None:
        """Перекрашивает валок в цвет состояния."""
        self.setBrush(QBrush(color))
        self.setPen(QPen(color.lighter(140), 1))


class MachineView(QWidget):
    """Центральная панель: схема машины с анимацией перемещения валков.

    Сигнал :attr:`animationFinished` позволяет главному окну дописать
    событие в журнал сессии после завершения предпросмотра.
    """

    animationFinished = Signal()

    def __init__(
        self,
        machine: MachineConfig,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._machine = machine
        self._current_gap = machine.min_gap
        self._target_gap: float | None = None
        self._pipe_diameter = machine.min_diameter
        self._status = STATUS_WAITING
        self._animation: QPropertyAnimation | None = None
        self._rollers: list[AnimatedRollers] = []

        # Параметры текущей анимации, нужны для промежуточных подписей.
        self._animation_start = machine.min_gap
        self._animation_target = machine.min_gap

        # Драйвер анимации создаётся до схемы, чтобы валки могли к нему обращаться.
        self._driver = OffsetDriver(self)

        self._build_ui()
        self._build_scene()
        self._driver.attach(self._rollers)
        self._apply_state()

    # ------------------------------------------------------------------
    # Построение интерфейса
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Создаёт вид со схемой и подпись под ним."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._view = QGraphicsView()
        self._view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._view.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._view.setMinimumHeight(330)
        self._view.setStyleSheet(
            "QGraphicsView { background-color: #1b1f24; border: 1px solid #3d4652;"
            " border-radius: 6px; }"
        )
        layout.addWidget(self._view, 1)

        caption = QLabel(
            "Демонстрационная схема. Геометрия условная, значение уставки модельное."
        )
        caption.setObjectName("HintLabel")
        caption.setWordWrap(True)
        layout.addWidget(caption)

    def _build_scene(self) -> None:
        """Создаёт элементы сцены: станок, трубу, валки и подписи."""
        scene = QGraphicsScene(0.0, 0.0, SCENE_WIDTH, SCENE_HEIGHT)
        self._scene = scene
        self._view.setScene(scene)

        frame = QGraphicsRectItem()
        frame.setRect(
            QRectF(FRAME_LEFT, FRAME_TOP, FRAME_RIGHT - FRAME_LEFT, FRAME_BOTTOM - FRAME_TOP)
        )
        frame.setPen(QPen(COLOR_FRAME, 1))
        frame.setBrush(QBrush(QColor("#23282f")))
        frame.setZValue(0)
        scene.addItem(frame)

        base = QGraphicsRectItem()
        base.setRect(
            QRectF(BASE_LEFT, BASE_TOP, BASE_RIGHT - BASE_LEFT, BASE_BOTTOM - BASE_TOP)
        )
        base.setPen(QPen(COLOR_FRAME, 1))
        base.setBrush(QBrush(QColor("#2a2f36")))
        base.setZValue(1)
        scene.addItem(base)

        title = self._text(self._machine.name, size=9, bold=True, color=COLOR_SECONDARY)
        title.setPos(LABEL_COLUMN_X, TITLE_Y)
        scene.addItem(title)

        self._pipe_item = QGraphicsRectItem()
        self._pipe_item.setPen(QPen(QColor("#cfd8e3"), 1))
        self._pipe_item.setBrush(QBrush(COLOR_PIPE))
        self._pipe_item.setZValue(3)
        scene.addItem(self._pipe_item)

        feed = self._text("подача →", size=8, color=COLOR_MUTED)
        feed.setPos(FRAME_RIGHT - 74.0, PIPE_AXIS_Y - 4.0)
        scene.addItem(feed)

        roller_count = max(1, min(len(ROLLER_POSITIONS), self._machine.roller_count))
        for index, x in enumerate(ROLLER_POSITIONS[:roller_count], start=1):
            top_roller = AnimatedRollers(x, is_top=True)
            bottom_roller = AnimatedRollers(x, is_top=False)
            scene.addItem(top_roller)
            scene.addItem(bottom_roller)
            self._rollers.append(top_roller)
            self._rollers.append(bottom_roller)

            label = self._text(f"№{index}", size=8, color=QColor("#cfd8e3"))
            label.setPos(x - 10.0, ROLLER_LABEL_Y)
            scene.addItem(label)

        # Размерная линия между валками первой позиции: стойка и две засечки.
        self._dimension_line = QGraphicsLineItem()
        self._dimension_tick_top = QGraphicsLineItem()
        self._dimension_tick_bottom = QGraphicsLineItem()
        for item in (
            self._dimension_line,
            self._dimension_tick_top,
            self._dimension_tick_bottom,
        ):
            item.setPen(QPen(COLOR_PREVIEW, 1))
            item.setZValue(4)
            scene.addItem(item)

        self._gap_caption = self._text(
            "Уставка между валками", size=8, color=COLOR_SECONDARY
        )
        self._gap_caption.setPos(LABEL_COLUMN_X, GAP_LABEL_Y - 46.0)
        scene.addItem(self._gap_caption)

        self._gap_line = self._text("", size=12, bold=True, color=COLOR_PREVIEW)
        self._gap_line.setPos(LABEL_COLUMN_X, GAP_LABEL_Y - 30.0)
        scene.addItem(self._gap_line)

        self._target_caption = self._text("Целевая уставка", size=8, color=COLOR_SECONDARY)
        self._target_caption.setPos(LABEL_COLUMN_X, GAP_LABEL_Y + 8.0)
        scene.addItem(self._target_caption)

        self._target_text = self._text("", size=11, bold=True, color=COLOR_APPLIED)
        self._target_text.setPos(LABEL_COLUMN_X, GAP_LABEL_Y + 24.0)
        scene.addItem(self._target_text)

        self._status_text = self._text(
            STATUS_WAITING, size=10, bold=True, color=COLOR_SECONDARY
        )
        self._status_text.setPos(LABEL_COLUMN_X, STATUS_Y)
        scene.addItem(self._status_text)

        disclaimer = self._text(
            "Демо-модель: перемещение валков условное, "
            "реальное оборудование не управляется.",
            size=8,
            color=COLOR_MUTED,
        )
        disclaimer.setPos(LABEL_COLUMN_X, DISCLAIMER_Y)
        scene.addItem(disclaimer)

        self._fit_scene()

    def _text(
        self,
        content: str,
        size: int,
        bold: bool = False,
        color: QColor = COLOR_SECONDARY,
    ) -> QGraphicsSimpleTextItem:
        """Создаёт подпись на схеме с единым шрифтом."""
        item = QGraphicsSimpleTextItem(content)
        font = QFont("Segoe UI")
        font.setPointSize(size)
        font.setBold(bold)
        item.setFont(font)
        item.setBrush(QBrush(color))
        item.setZValue(7)
        return item

    # ------------------------------------------------------------------
    # Внешнее управление
    # ------------------------------------------------------------------

    def set_pipe_diameter(self, diameter: float) -> None:
        """Обновляет толщину трубы на схеме."""
        self._pipe_diameter = diameter
        self._layout_static_items()
        self._apply_state()

    def reset_to_machine_minimum(self) -> None:
        """Возвращает схему в исходное положение."""
        self.stop_animation()
        self._target_gap = None
        self._current_gap = self._machine.min_gap
        self._set_all_offsets(self._current_gap)
        self._status = STATUS_WAITING
        self._apply_state()

    def preview_to(self, final_gap: float, status: str = STATUS_CALCULATED) -> None:
        """Плавно перемещает валки к целевой уставке (предпросмотр)."""
        self._target_gap = final_gap
        self._status = status
        self._start_animation(final_gap, COLOR_PREVIEW)

    def mark_applied(self) -> None:
        """Фиксирует применённое состояние: валки зелёные."""
        self.stop_animation()
        if self._target_gap is not None:
            self._current_gap = self._target_gap
            self._set_all_offsets(self._current_gap)
        self._status = STATUS_APPLIED
        self._apply_state(COLOR_APPLIED)

    def mark_manual(self) -> None:
        """Фиксирует состояние ручной коррекции."""
        self.stop_animation()
        if self._target_gap is not None:
            self._current_gap = self._target_gap
            self._set_all_offsets(self._current_gap)
        self._status = STATUS_MANUAL
        self._apply_state(COLOR_PREVIEW)

    def mark_error(self, message: str = "") -> None:
        """Переводит схему в состояние ошибки параметров."""
        self.stop_animation()
        self._target_gap = None
        self._status = STATUS_ERROR
        self._apply_state(COLOR_ERROR)
        if message:
            self._status_text.setText(f"{STATUS_ERROR}: {message}")

    def mark_waiting(self) -> None:
        """Переводит схему в состояние ожидания расчёта."""
        self.stop_animation()
        self._target_gap = None
        self._status = STATUS_WAITING
        self._apply_state()

    def stop_animation(self) -> None:
        """Останавливает текущую анимацию, если она идёт."""
        if self._animation is not None:
            self._animation.stop()
            self._animation = None

    # ------------------------------------------------------------------
    # Анимация
    # ------------------------------------------------------------------

    def _start_animation(self, final_gap: float, color: QColor) -> None:
        """Запускает анимацию вертикального смещения валков."""
        self.stop_animation()
        self._apply_state(color)
        self._set_all_offsets(self._current_gap)

        if abs(final_gap - self._current_gap) < 0.05:
            self._current_gap = final_gap
            self._set_all_offsets(final_gap)
            self._apply_state(color)
            self.animationFinished.emit()
            return

        self._animation_start = self._current_gap
        self._animation_target = final_gap

        animation = QPropertyAnimation(self._driver, b"value_property")
        animation.setDuration(ANIMATION_DURATION_MS)
        animation.setStartValue(self._current_gap * GAP_SCALE)
        animation.setEndValue(final_gap * GAP_SCALE)
        animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        animation.valueChanged.connect(self._on_animation_step)
        animation.finished.connect(self._on_animation_finished)
        self._animation = animation
        animation.start()

    def _on_animation_step(self, value: float) -> None:
        """Обновляет подписи уставки по ходу анимации."""
        progress_gap = value / GAP_SCALE
        span = self._animation_target - self._animation_start
        if abs(span) > 1e-6:
            share = (progress_gap - self._animation_start) / span
        else:
            share = 1.0
        share = max(0.0, min(1.0, share))
        self._current_gap = self._animation_start + span * share

        self._gap_line.setText(f"Уставка: {format_mm(self._current_gap)}")
        self._gap_line.setText(f"{format_mm(self._current_gap)}")
        self._target_text.setText(
            f"{format_mm(self._animation_target)} ({int(share * 100)}%)"
        )
        self._target_text.setBrush(QBrush(COLOR_PREVIEW))

    def _on_animation_finished(self) -> None:
        """Фиксирует конечное положение валков."""
        self._animation = None
        self._current_gap = self._animation_target
        self._set_all_offsets(self._animation_target)
        self._apply_state()
        self.animationFinished.emit()

    def _set_all_offsets(self, gap: float) -> None:
        """Мгновенно ставит все валки в положение по уставке."""
        offset = gap * GAP_SCALE
        for roller in self._rollers:
            roller.set_offset(offset)
        self._layout_static_items()

    # ------------------------------------------------------------------
    # Отрисовка значений
    # ------------------------------------------------------------------

    def _apply_state(self, override: QColor | None = None) -> None:
        """Обновляет цвета и подписи согласно текущему состоянию."""
        color = override if override is not None else self._color_for_status(self._status)
        for roller in self._rollers:
            roller.apply_color(color)

        dimension_pen = QPen(color.lighter(120), 1)
        for item in (
            self._dimension_line,
            self._dimension_tick_top,
            self._dimension_tick_bottom,
        ):
            item.setPen(dimension_pen)

        self._status_text.setText(self._status)
        self._status_text.setBrush(QBrush(self._status_color()))
        self._apply_gap_text()
        self._layout_static_items()

    def _color_for_status(self, status: str) -> QColor:
        """Возвращает цвет валков для указанного статуса."""
        if status == STATUS_APPLIED:
            return COLOR_APPLIED
        if status in (STATUS_CALCULATED, STATUS_MANUAL):
            return COLOR_PREVIEW
        if status == STATUS_ERROR:
            return COLOR_ERROR
        return COLOR_IDLE

    def _status_color(self) -> QColor:
        """Возвращает цвет подписи статуса."""
        if self._status == STATUS_APPLIED:
            return COLOR_APPLIED
        if self._status in (STATUS_CALCULATED, STATUS_MANUAL):
            return COLOR_PREVIEW
        if self._status == STATUS_ERROR:
            return COLOR_ERROR
        return COLOR_SECONDARY

    def _fit_scene(self) -> None:
        """Вписывает сцену в вид с сохранением пропорций."""
        if self._scene.sceneRect().isEmpty():
            return
        self._view.fitInView(
            self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio
        )

    def resizeEvent(self, event: object) -> None:  # type: ignore[override]
        """Пересчитывает масштаб схемы при изменении размера панели."""
        super().resizeEvent(event)  # type: ignore[arg-type]
        self._fit_scene()

    def _apply_gap_text(self) -> None:
        """Обновляет подписи текущей и целевой уставки."""
        self._gap_line.setText(format_mm(self._current_gap))
        if self._target_gap is None:
            self._target_text.setText("нет расчёта")
            self._target_text.setBrush(QBrush(COLOR_SECONDARY))
            return
        self._target_text.setText(format_mm(self._target_gap))
        self._target_text.setBrush(QBrush(COLOR_APPLIED))

    def _layout_static_items(self) -> None:
        """Располагает трубу и размерную линию по текущему смещению."""
        pipe_width = PIPE_BASE_WIDTH + max(
            0.0, self._pipe_diameter - 20.0
        ) * PIPE_WIDTH_PER_MM
        max_width = FRAME_RIGHT - FRAME_LEFT - 40.0
        self._pipe_item.setRect(
            QRectF(
                FRAME_LEFT + 20.0,
                PIPE_AXIS_Y - 13.0,
                min(pipe_width, max_width),
                26.0,
            )
        )

        # Размерная линия идёт между рабочими поверхностями валков первой
        # позиции: от нижней грани верхнего валка до верхней грани нижнего.
        dimension_x = ROLLER_POSITIONS[0] - ROLLER_WIDTH / 2 - 9.0
        tick = 7.0
        offset = self._rollers[0].offset()
        top_contact = PIPE_AXIS_Y - offset + ROLLER_HEIGHT / 2
        bottom_contact = PIPE_AXIS_Y + offset - ROLLER_HEIGHT / 2
        self._dimension_line.setLine(
            dimension_x, top_contact, dimension_x, bottom_contact
        )
        self._dimension_tick_top.setLine(
            dimension_x - tick, top_contact, dimension_x + tick, top_contact
        )
        self._dimension_tick_bottom.setLine(
            dimension_x - tick, bottom_contact, dimension_x + tick, bottom_contact
        )