"""Вкладка «Журнал»: таблица переналадок, фильтр и экспорт."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.journal_service import COLUMNS, JournalService
from app.utils.formatting import format_minutes

#: Предлагаемое имя файла при экспорте.
DEFAULT_EXPORT_NAME = "journal_export.csv"

#: Максимальное число отображаемых строк за одну сессию.
MAX_VISIBLE_ROWS = 500


class JournalTab(QWidget):
    """Показывает журнал переналадок в виде таблицы.

    Данные читаются напрямую из файла журнала, поэтому таблица
    показывает историю между запусками приложения.
    """

    def __init__(
        self,
        journal: JournalService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._journal = journal
        self._all_records: list[dict[str, object]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QLabel("Журнал переналадок")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        layout.addWidget(self._build_toolbar())
        layout.addWidget(self._build_table(), 1)

        self.status_label = QLabel()
        self.status_label.setObjectName("HintLabel")
        layout.addWidget(self.status_label)

        self.refresh()

    def _build_toolbar(self) -> QWidget:
        """Панель фильтра и кнопок обслуживания журнала."""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        filter_label = QLabel("Фильтр:")
        filter_label.setObjectName("FieldLabel")
        layout.addWidget(filter_label)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText(
            "Номер заказа, партия, оператор, операция, марка стали"
        )
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(self._apply_filter)
        layout.addWidget(self.filter_edit, 1)

        refresh_button = QPushButton("Обновить")
        refresh_button.clicked.connect(self.refresh)
        layout.addWidget(refresh_button)

        export_button = QPushButton("Экспорт CSV")
        export_button.setToolTip("Сохранить журнал в файл для Excel")
        export_button.clicked.connect(self._export_csv)
        layout.addWidget(export_button)

        clear_button = QPushButton("Очистить журнал")
        clear_button.setObjectName("DangerButton")
        clear_button.setToolTip(
            "Очистить журнал с подтверждением.\n"
            "Перед очисткой создаётся резервная копия journal.backup.json"
        )
        clear_button.clicked.connect(self._clear_journal)
        layout.addWidget(clear_button)

        return container

    def _build_table(self) -> QTableWidget:
        """Таблица записей журнала."""
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(list(COLUMNS))
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(False)
        self.table.setSortingEnabled(False)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(9, QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)

        # Последние записи важнее: показываем свежие сверху.
        self.table.verticalHeader().setDefaultSectionSize(30)
        return self.table

    def refresh(self) -> None:
        """Перечитывает журнал и обновляет таблицу."""
        self._all_records = list(self._journal.load())
        self._fill_table(self._all_records)
        self._update_status(len(self._all_records))

    def _apply_filter(self, query: str) -> None:
        """Применяет фильтр к таблице."""
        filtered = self._journal.filter_records(self._all_records, query)
        self._fill_table(filtered)
        self._update_status(len(self._all_records), len(filtered))

    def _fill_table(self, records: list[dict[str, object]]) -> None:
        """Заполняет таблицу строками журнала."""
        rows = self._journal.rows_for_table(records)
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column_index, value in enumerate(row):
                item = QTableWidgetItem(value)
                if column_index in (4, 5, 8, 9, 10):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                else:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                    )
                self.table.setItem(row_index, column_index, item)
            self._colorize_row(row_index, row)
        self.table.resizeColumnsToContents()

    def _colorize_row(self, row_index: int, row: list[str]) -> None:
        """Подкрашивает строку по уровню риска для быстрого чтения."""
        from PySide6.QtGui import QColor

        risk_index = COLUMNS.index("Риск")
        risk = row[risk_index]
        if risk == "высокий":
            color = QColor("#e74c3c")
        elif risk == "средний":
            color = QColor("#f1c40f")
        else:
            color = QColor("#2ecc71")
        risk_item = self.table.item(row_index, risk_index)
        if risk_item is not None:
            risk_item.setForeground(color)

    def _update_status(self, total: int, shown: int | None = None) -> None:
        """Обновляет подпись с количеством записей."""
        saved = self._journal.aggregates(self._all_records)
        parts = [f"Записей всего: {total}"]
        if shown is not None and shown != total:
            parts.append(f"после фильтра: {shown}")
        parts.append(f"суммарная экономия: {format_minutes(float(saved['saved_total']))}")
        parts.append(f"ручных коррекций: {int(saved['manual_overrides'])}")
        parts.append(f"применений с высоким риском: {int(saved['high_risk'])}")
        self.status_label.setText(" · ".join(parts))

    def _export_csv(self) -> None:
        """Экспортирует журнал в CSV через диалог выбора файла."""
        records = self._journal.filter_records(
            self._all_records, self.filter_edit.text()
        )
        if not records:
            QMessageBox.information(
                self,
                "Экспорт журнала",
                "Нет записей для экспорта. Сначала выполните расчёт и примените настройку.",
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Экспорт журнала в CSV", DEFAULT_EXPORT_NAME, "CSV (*.csv)"
        )
        if not path:
            return

        try:
            header, rows = self._journal.csv_rows(records)
            from app.services.report_service import write_csv

            written = write_csv(path, header, rows)
        except OSError as exc:
            QMessageBox.critical(
                self,
                "Ошибка экспорта",
                f"Не удалось сохранить файл {Path(path).name}:\n{exc}",
            )
            return

        QMessageBox.information(
            self,
            "Экспорт завершён",
            f"Журнал сохранён в файл:\n{written}\n\n"
            f"Записей: {len(rows)}. Файл открывается в Excel "
            "с разделителем «;» и кириллицей.",
        )

    def _clear_journal(self) -> None:
        """Очищает журнал с подтверждением и резервной копией."""
        if not self._all_records:
            QMessageBox.information(
                self, "Очистка журнала", "Журнал уже пуст."
            )
            return

        answer = QMessageBox.question(
            self,
            "Очистка журнала",
            f"Удалить все записи журнала ({len(self._all_records)} шт.)?\n\n"
            "Перед очисткой будет создана резервная копия journal.backup.json "
            "в каталоге данных приложения.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        success, message = self._journal.clear()
        if not success:
            QMessageBox.critical(self, "Ошибка очистки", message)
            return

        self.refresh()
        QMessageBox.information(self, "Журнал очищен", message)

    def latest_record(self) -> dict[str, object] | None:
        """Возвращает последнюю запись журнала."""
        if not self._all_records:
            return None
        return self._all_records[-1]