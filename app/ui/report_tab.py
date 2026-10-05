"""Вкладка «Отчёт»: презентационный dashboard по последнему применению."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.models.machine import MachineConfig
from app.models.pipe import Pipe
from app.models.result import RISK_HIGH, RISK_LOW, RISK_MEDIUM, CalculationResult
from app.services.journal_service import JournalService
from app.services.report_service import (
    build_summary,
    comparison_rows,
    report_csv,
    write_text,
)
from app.utils.formatting import format_minutes

#: Предлагаемое имя файла отчёта. Имя заказа делает выгрузки удобнее
#: для поиска, поэтому добавляется к базовому имени.
DEFAULT_REPORT_NAME = "report_setup.csv"

#: Предлагаемое имя текстового отчёта.
DEFAULT_TEXT_REPORT_NAME = "report_setup.txt"

#: Символы, которые нельзя использовать в имени файла.
_UNSAFE_NAME_CHARS = '\\/:*?"<>|'


def build_suggested_name(base: str, order_no: str, extension: str) -> str:
    """Собирает безопасное имя файла вида ``base_ДЕМО-002.csv``.

    Номер заказа помогает находить выгрузки, а очистка символов
    гарантирует, что Windows не отклонит путь.
    """
    cleaned = "".join(
        "_" if character in _UNSAFE_NAME_CHARS else character for character in order_no
    ).strip()
    cleaned = cleaned.strip(". ")
    stem = Path(base).stem or base
    if not cleaned:
        return f"{stem}.{extension}"
    return f"{stem}_{cleaned}.{extension}"


class ReportTab(QWidget):
    """Сводный отчёт: метрики, сравнение «как есть / как будет», журнал.

    Данные берутся из последнего применённого расчёта и агрегатов
    журнала, поэтому отчёт отвечает на вопрос «что дал проект».
    """

    def __init__(
        self,
        machine: MachineConfig,
        journal: JournalService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._machine = machine
        self._journal = journal

        self._pipe: Pipe | None = None
        self._result: CalculationResult | None = None
        self._applied = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        layout.addWidget(self._build_header())
        layout.addWidget(self._build_cards())
        layout.addWidget(self._build_comparison(), 1)
        layout.addWidget(self._build_journal_stats())
        layout.addWidget(self._build_toolbar())

        self.show_empty()

    # ------------------------------------------------------------------
    # Построение
    # ------------------------------------------------------------------

    def _build_header(self) -> QWidget:
        """Заголовок с указанием источника данных отчёта."""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("Отчёт по переналадке")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)
        layout.addStretch(1)

        self.source_label = QLabel("Данные по последнему применению не загружены")
        self.source_label.setObjectName("HintLabel")
        layout.addWidget(self.source_label)
        return container

    def _build_cards(self) -> QWidget:
        """Ряд карточек с ключевыми метриками."""
        container = QWidget()
        grid = QGridLayout(container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(10)

        self._card_values: dict[str, QLabel] = {}
        self._card_captions: dict[str, QLabel] = {}
        definitions = (
            ("time_saved", "Экономия времени", "min"),
            ("trials", "Снижение пробных прогонов", "шт."),
            ("defect", "Прогноз брака", "%"),
            ("risk", "Уровень риска", ""),
            ("final_gap", "Итоговая уставка", "мм"),
        )
        for index, (key, caption, unit) in enumerate(definitions):
            frame, value_label, caption_label = self._build_card(caption, unit)
            self._card_values[key] = value_label
            self._card_captions[key] = caption_label
            grid.addWidget(frame, 0, index)
            grid.setColumnStretch(index, 1)
        return container

    def _build_card(self, caption: str, unit: str) -> tuple[QFrame, QLabel, QLabel]:
        """Создаёт одну карточку метрики."""
        frame = QFrame()
        frame.setObjectName("MetricCard")
        frame.setMinimumHeight(104)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        caption_label = QLabel(caption)
        caption_label.setObjectName("FieldLabel")
        caption_label.setWordWrap(True)
        layout.addWidget(caption_label)

        value_label = QLabel("—")
        value_label.setObjectName("ValueLabel")
        value_label.setStyleSheet("font-size: 20pt; font-weight: bold;")
        layout.addWidget(value_label)

        unit_label = QLabel(unit)
        unit_label.setObjectName("HintLabel")
        layout.addWidget(unit_label)
        return frame, value_label, unit_label

    def _build_comparison(self) -> QGroupBox:
        """Таблица сравнения «как есть / как будет»."""
        box = QGroupBox("Сравнение: как есть / как будет")
        layout = QVBoxLayout(box)
        layout.setSpacing(8)

        self.comparison_table = QTableWidget(0, 3)
        self.comparison_table.setHorizontalHeaderLabels(
            ["Показатель", "Как есть (ручная переналадка)", "Как будет (с программой)"]
        )
        self.comparison_table.verticalHeader().setVisible(False)
        self.comparison_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.comparison_table.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection
        )
        self.comparison_table.setAlternatingRowColors(True)
        header = self.comparison_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.comparison_table)

        self.empty_label = QLabel(
            "Отчёт появится после применения настройки на вкладке «Переналадка»."
        )
        self.empty_label.setObjectName("HintLabel")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_label)

        return box

    def _build_journal_stats(self) -> QGroupBox:
        """Агрегированные показатели по журналу."""
        box = QGroupBox("Агрегированные данные по журналу")
        grid = QGridLayout(box)
        grid.setSpacing(8)

        self._stat_values: dict[str, QLabel] = {}
        definitions = (
            ("total", "Всего переналадок"),
            ("saved_total", "Суммарная экономия времени"),
            ("saved_average", "Средняя экономия"),
            ("manual", "Ручных коррекций"),
            ("high_risk", "Применений с высоким риском"),
        )
        for index, (key, caption) in enumerate(definitions):
            caption_label = QLabel(caption)
            caption_label.setObjectName("FieldLabel")
            value_label = QLabel("0")
            value_label.setObjectName("ValueLabel")
            grid.addWidget(caption_label, 0, index)
            grid.addWidget(value_label, 1, index)
            grid.setColumnStretch(index, 1)
            self._stat_values[key] = value_label
        return box

    def _build_toolbar(self) -> QWidget:
        """Кнопки обслуживания отчёта."""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        refresh_button = QPushButton("Обновить отчёт")
        refresh_button.clicked.connect(self.refresh)
        layout.addWidget(refresh_button)

        export_button = QPushButton("Экспорт отчёта в CSV")
        export_button.setObjectName("PrimaryButton")
        export_button.setToolTip(
            "Сохранить сводный отчёт: исходные данные, расчёт, сравнение, агрегаты"
        )
        export_button.clicked.connect(self._export_report_csv)
        layout.addWidget(export_button)

        export_journal_button = QPushButton("Экспорт журнала в CSV")
        export_journal_button.clicked.connect(self._export_journal_csv)
        layout.addWidget(export_journal_button)

        text_button = QPushButton("Сохранить текстовый отчёт")
        text_button.setToolTip("Полный отчёт в виде текстового файла для печати")
        text_button.clicked.connect(self._export_text_report)
        layout.addWidget(text_button)

        layout.addStretch(1)
        return container

    # ------------------------------------------------------------------
    # Данные
    # ------------------------------------------------------------------

    def set_result(self, pipe: Pipe, result: CalculationResult, applied: bool) -> None:
        """Передаёт отчёту последний расчёт."""
        self._pipe = pipe
        self._result = result
        self._applied = applied
        self.refresh()

    def show_empty(self) -> None:
        """Показывает пустое состояние отчёта."""
        self.refresh()

    def refresh(self) -> None:
        """Пересчитывает содержимое отчёта."""
        aggregates = self._journal.aggregates(self._journal.load())
        self._fill_stats(aggregates)

        if self._result is None or self._pipe is None:
            self._fill_cards_empty()
            self.comparison_table.setRowCount(0)
            self.empty_label.setVisible(True)
            self.source_label.setText("Данные по последнему применению не загружены")
            return

        summary = build_summary(self._result, self._pipe, self._machine, aggregates)
        self._fill_cards(summary)
        self._fill_comparison()
        self.empty_label.setVisible(False)

        state = "применено" if self._applied else "рассчитано, не применено"
        self.source_label.setText(
            f"Источник: {self._pipe.order_no}, {self._pipe.designation}, "
            f"{self._pipe.material} — {state}"
        )

    def _fill_cards_empty(self) -> None:
        """Сбрасывает карточки метрик."""
        for label in self._card_values.values():
            label.setText("—")

    def _fill_cards(self, summary: dict[str, object]) -> None:
        """Заполняет карточки метрик значениями."""
        self._card_values["time_saved"].setText(str(summary["time_saved"]))
        self._card_values["trials"].setText(
            f"{summary['trial_runs_reduction']} "
            f"({summary['trial_runs_to_be']} вместо {summary['trial_runs_as_is']})"
        )
        self._card_values["defect"].setText(str(summary["defect_to_be"]))
        self._card_values["final_gap"].setText(str(summary["final_gap"]))

        risk_value = self._card_values["risk"]
        risk = str(summary["risk"])
        risk_value.setText(risk)
        if risk == RISK_LOW:
            risk_value.setStyleSheet("color: #2ecc71; font-size: 20pt; font-weight: bold;")
        elif risk == RISK_MEDIUM:
            risk_value.setStyleSheet("color: #f1c40f; font-size: 20pt; font-weight: bold;")
        else:
            risk_value.setStyleSheet("color: #e74c3c; font-size: 20pt; font-weight: bold;")

    def _fill_stats(self, aggregates: dict[str, float]) -> None:
        """Заполняет агрегированные показатели журнала."""
        self._stat_values["total"].setText(str(int(aggregates.get("total", 0))))
        self._stat_values["saved_total"].setText(
            format_minutes(float(aggregates.get("saved_total", 0.0)))
        )
        self._stat_values["saved_average"].setText(
            format_minutes(float(aggregates.get("saved_average", 0.0)))
        )
        self._stat_values["manual"].setText(
            str(int(aggregates.get("manual_overrides", 0)))
        )
        self._stat_values["high_risk"].setText(
            str(int(aggregates.get("high_risk", 0)))
        )

    def _fill_comparison(self) -> None:
        """Заполняет таблицу сравнения по последнему расчёту."""
        if self._result is None:
            self.comparison_table.setRowCount(0)
            return
        rows = comparison_rows(self._result)
        self.comparison_table.setRowCount(len(rows))
        for row_index, (title, before, after) in enumerate(rows):
            self.comparison_table.setItem(row_index, 0, QTableWidgetItem(title))
            before_item = QTableWidgetItem(before)
            before_item.setForeground(QColor("#e74c3c"))
            self.comparison_table.setItem(row_index, 1, before_item)
            after_item = QTableWidgetItem(after)
            after_item.setForeground(QColor("#2ecc71"))
            self.comparison_table.setItem(row_index, 2, after_item)
        self.comparison_table.resizeRowsToContents()

    # ------------------------------------------------------------------
    # Экспорт
    # ------------------------------------------------------------------

    def _suggested_name(self, order_no: str, extension: str = "csv") -> str:
        """Имя файла выгрузки с номером заказа."""
        return build_suggested_name(DEFAULT_REPORT_NAME, order_no, extension)

    def _export_report_csv(self) -> None:
        """Экспортирует сводный отчёт в CSV."""
        if self._result is None or self._pipe is None:
            QMessageBox.information(
                self,
                "Экспорт отчёта",
                "Сначала выполните расчёт и примените настройку на вкладке «Переналадка».",
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Экспорт отчёта в CSV",
            self._suggested_name(self._pipe.order_no),
            "CSV (*.csv)",
        )
        if not path:
            return
        try:
            aggregates = self._journal.aggregates(self._journal.load())
            written = report_csv(
                path, self._result, self._pipe, self._machine, aggregates
            )
        except OSError as exc:
            QMessageBox.critical(
                self, "Ошибка экспорта", f"Не удалось сохранить {Path(path).name}:\n{exc}"
            )
            return
        QMessageBox.information(
            self,
            "Экспорт завершён",
            f"Отчёт сохранён:\n{written}\n\n"
            "Файл в кодировке utf-8-sig, разделитель «;» — открывается в Excel.",
        )

    def _export_journal_csv(self) -> None:
        """Экспортирует журнал в CSV."""
        records = self._journal.load()
        if not records:
            QMessageBox.information(
                self, "Экспорт журнала", "Журнал пуст: записей пока нет."
            )
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Экспорт журнала в CSV", "journal_export.csv", "CSV (*.csv)"
        )
        if not path:
            return
        try:
            header, rows = self._journal.csv_rows(records)
            from app.services.report_service import write_csv

            written = write_csv(path, header, rows)
        except OSError as exc:
            QMessageBox.critical(
                self, "Ошибка экспорта", f"Не удалось сохранить {Path(path).name}:\n{exc}"
            )
            return
        QMessageBox.information(
            self, "Экспорт завершён", f"Журнал сохранён:\n{written}"
        )

    def _export_text_report(self) -> None:
        """Сохраняет текстовый отчёт."""
        if self._result is None or self._pipe is None:
            QMessageBox.information(
                self, "Отчёт", "Сначала выполните расчёт на вкладке «Переналадка»."
            )
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранение текстового отчёта",
            self._suggested_name(self._pipe.order_no, "txt"),
            "Текст (*.txt)",
        )
        if not path:
            return
        try:
            aggregates = self._journal.aggregates(self._journal.load())
            from app.services.report_service import build_report_text

            text = build_report_text(
                self._result, self._pipe, self._machine, aggregates
            )
            written = write_text(path, text)
        except OSError as exc:
            QMessageBox.critical(
                self, "Ошибка сохранения", f"Не удалось сохранить {Path(path).name}:\n{exc}"
            )
            return
        QMessageBox.information(
            self, "Отчёт сохранён", f"Текстовый отчёт сохранён:\n{written}"
        )