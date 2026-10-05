"""Журнал переналадок: сохранение в JSON и защита от повреждения файла.

Файл журнала хранится в пользовательском каталоге приложения
(``%APPDATA%/PipeAlign``), а не рядом с ``.exe``: папка с программой
может быть недоступна для записи.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.models.machine import MachineConfig
from app.models.pipe import Pipe
from app.models.result import CalculationResult
from app.utils.formatting import now_iso
from app.utils.paths import journal_path

#: Имя файла, куда переносится повреждённый журнал.
BAD_JOURNAL_NAME = "journal.bad.json"

#: Имя файла резервной копии при очистке журнала.
BACKUP_JOURNAL_NAME = "journal.backup.json"

#: Статусы записи журнала.
STATUS_CALCULATED = "Расчёт"
STATUS_APPLIED = "Применено"
STATUS_MANUAL = "Ручная коррекция"
STATUS_CANCELLED = "Отменено"

#: Колонки таблицы журнала в порядке отображения.
COLUMNS: tuple[str, ...] = (
    "Время",
    "Заказ",
    "Партия",
    "Оператор",
    "Диаметр",
    "Стенка",
    "Материал",
    "Операция",
    "Изгиб",
    "Итоговая уставка",
    "Проходы",
    "Риск",
    "Статус",
    "Примечание",
)

#: Соответствие «ключ записи -> заголовок колонки» для экспорта CSV.
COLUMN_FIELDS: dict[str, str] = {
    "Время": "timestamp",
    "Заказ": "order_no",
    "Партия": "batch",
    "Оператор": "operator",
    "Диаметр": "diameter",
    "Стенка": "wall_thickness",
    "Материал": "material",
    "Операция": "operation",
    "Изгиб": "deflection",
    "Итоговая уставка": "final_gap",
    "Проходы": "passes",
    "Риск": "risk_level",
    "Статус": "status",
    "Примечание": "note",
}


class JournalService:
    """Чтение и запись журнала переналадок.

    Все операции безопасны: повреждённый файл откладывается в
    ``journal.bad.json`` и создаётся новый пустой журнал, чтобы
    приложение никогда не падало из-за данных на диске.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = Path(path) if path is not None else journal_path()
        #: Сообщения о восстановлении, которые показываются в UI после старта.
        self.startup_warnings: list[str] = []

    @property
    def path(self) -> Path:
        """Путь к файлу журнала."""
        return self._path

    def load(self) -> list[dict[str, Any]]:
        """Возвращает записи журнала, восстанавливая повреждённый файл."""
        if not self._path.exists():
            self.startup_warnings = []
            return []
        try:
            with self._path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            self._quarantine_broken_file("файл журнала повреждён и не мог быть разобран")
            return []
        if not isinstance(data, list):
            self._quarantine_broken_file("файл журнала имеет неверную структуру")
            return []
        self.startup_warnings = []
        return [item for item in data if isinstance(item, dict)]

    def _quarantine_broken_file(self, reason: str) -> None:
        """Переименовывает повреждённый журнал и создаёт пустой новый."""
        bad_path = self._path.parent / BAD_JOURNAL_NAME
        message = f"Журнал переналадок {reason}. Повреждённый файл сохранён как {bad_path.name}."
        moved = False
        try:
            os.replace(self._path, bad_path)
            moved = True
        except OSError:
            moved = False
        if not moved:
            # Файл не удалось переименовать (например, занят другим
            # процессом) — удаляем его, чтобы создался чистый журнал.
            try:
                self._path.unlink(missing_ok=True)
            except OSError as exc:
                message += f" Не удалось удалить повреждённый файл: {exc}."
        self._write([])
        self.startup_warnings = [message]

    def _write(self, records: list[dict[str, Any]]) -> bool:
        """Атомарно записывает список записей в файл журнала."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._path.with_suffix(".tmp")
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(records, handle, ensure_ascii=False, indent=2)
            os.replace(temporary, self._path)
            return True
        except OSError as exc:
            self.startup_warnings = [f"Не удалось записать журнал: {exc}"]
            return False

    def append(self, record: dict[str, Any]) -> bool:
        """Добавляет запись в конец журнала."""
        records = self.load()
        records.append(record)
        return self._write(records)

    def add_entry(
        self,
        pipe: Pipe,
        result: CalculationResult,
        status: str,
        note: str = "",
    ) -> dict[str, Any]:
        """Формирует и сохраняет запись журнала по расчёту."""
        record: dict[str, Any] = {
            "timestamp": now_iso(),
            "order_no": pipe.order_no,
            "batch": pipe.batch,
            "operator": pipe.operator,
            "diameter": pipe.diameter,
            "wall_thickness": pipe.wall_thickness,
            "material": pipe.material,
            "length": pipe.length,
            "operation": pipe.operation,
            "has_deflection": pipe.has_deflection,
            "deflection": pipe.deflection,
            "base_gap": result.base_gap,
            "material_correction": result.material_correction,
            "deflection_correction": result.deflection_correction,
            "final_gap": result.final_gap,
            "passes": result.passes,
            "feed_speed": result.feed_speed,
            "risk_level": result.risk_level,
            "as_is_time_minutes": result.as_is_time_minutes,
            "to_be_time_minutes": result.to_be_time_minutes,
            "time_saved_minutes": result.time_saved_minutes,
            "as_is_trial_runs": result.as_is_trial_runs,
            "to_be_trial_runs": result.to_be_trial_runs,
            "as_is_defect_percent": result.as_is_defect_percent,
            "to_be_defect_percent": result.to_be_defect_percent,
            "status": status,
            "manual_override": result.manual_override,
            "manual_reason": result.manual_reason,
            "warnings": list(result.warnings),
            "note": note,
        }
        self.append(record)
        return record

    def clear(self) -> tuple[bool, str]:
        """Очищает журнал, предварительно создав резервную копию.

        Возвращает ``(успех, сообщение)`` для показа в интерфейсе.
        """
        try:
            if self._path.exists():
                backup = self._path.parent / BACKUP_JOURNAL_NAME
                os.replace(self._path, backup)
            ok = self._write([])
        except OSError as exc:
            return False, f"Не удалось очистить журнал: {exc}"
        if ok:
            return True, f"Журнал очищен. Резервная копия: {BACKUP_JOURNAL_NAME}"
        return False, "Не удалось записать пустой журнал."

    def filter_records(
        self, records: list[dict[str, Any]], query: str
    ) -> list[dict[str, Any]]:
        """Фильтрует записи по номеру заказа, партии, оператору и операции."""
        needle = query.strip().lower()
        if not needle:
            return list(records)
        fields = ("order_no", "batch", "operator", "operation", "material", "status")
        matched: list[dict[str, Any]] = []
        for record in records:
            haystack = " ".join(
                str(record.get(field, "")) for field in fields
            ).lower()
            if needle in haystack:
                matched.append(record)
        return matched

    def aggregates(self, records: list[dict[str, Any]]) -> dict[str, float]:
        """Считает сводные показатели журнала для вкладки «Отчёт»."""
        total = len(records)
        saved = 0.0
        manual = 0
        high_risk = 0
        applied = 0
        for record in records:
            status = str(record.get("status", ""))
            as_is = float(record.get("as_is_time_minutes", 0.0) or 0.0)
            to_be = float(record.get("to_be_time_minutes", 0.0) or 0.0)
            saved += max(0.0, as_is - to_be)
            if record.get("manual_override"):
                manual += 1
            if str(record.get("risk_level", "")) == "высокий":
                high_risk += 1
            if status == STATUS_APPLIED:
                applied += 1
        return {
            "total": total,
            "applied": applied,
            "saved_total": round(saved, 1),
            "saved_average": round(saved / total, 1) if total else 0.0,
            "manual_overrides": manual,
            "high_risk": high_risk,
        }

    def rows_for_table(self, records: list[dict[str, Any]]) -> list[list[str]]:
        """Готовит строки для QTableWidget по колонкам :data:`COLUMNS`."""
        from app.utils.formatting import (
            format_diameter,
            format_int,
            format_timestamp,
        )

        rows: list[list[str]] = []
        for record in records:
            deflection = record.get("deflection", 0.0) or 0.0
            has_deflection = bool(record.get("has_deflection", False))
            risk = str(record.get("risk_level", ""))
            row = [
                format_timestamp(str(record.get("timestamp", ""))),
                str(record.get("order_no", "")),
                str(record.get("batch", "")),
                str(record.get("operator", "")),
                format_diameter(float(record.get("diameter", 0.0) or 0.0)),
                format_diameter(float(record.get("wall_thickness", 0.0) or 0.0)),
                str(record.get("material", "")),
                str(record.get("operation", "")),
                format_diameter(float(deflection)) if has_deflection else "—",
                format_diameter(float(record.get("final_gap", 0.0) or 0.0)),
                format_int(float(record.get("passes", 0) or 0)),
                risk,
                str(record.get("status", "")),
                str(record.get("note", "")),
            ]
            rows.append(row)
        return rows

    def csv_rows(self, records: list[dict[str, Any]]) -> tuple[list[str], list[list[str]]]:
        """Готовит заголовок и строки для экспорта журнала в CSV."""
        from app.utils.formatting import (
            format_diameter,
            format_int,
            format_timestamp,
        )

        header = [
            "Время",
            "Заказ",
            "Партия",
            "Оператор",
            "Диаметр, мм",
            "Стенка, мм",
            "Марка стали",
            "Операция",
            "Есть изгиб",
            "Изгиб, мм/м",
            "Базовая уставка, мм",
            "Поправка материал, мм",
            "Поправка изгиб, мм",
            "Итоговая уставка, мм",
            "Проходы",
            "Скорость, м/мин",
            "Риск",
            "Статус",
            "Ручная коррекция",
            "Причина",
            "Предупреждения",
        ]
        rows: list[list[str]] = []
        for record in records:
            warnings = record.get("warnings", []) or []
            rows.append(
                [
                    format_timestamp(str(record.get("timestamp", ""))),
                    str(record.get("order_no", "")),
                    str(record.get("batch", "")),
                    str(record.get("operator", "")),
                    format_diameter(float(record.get("diameter", 0.0) or 0.0)),
                    format_diameter(float(record.get("wall_thickness", 0.0) or 0.0)),
                    str(record.get("material", "")),
                    str(record.get("operation", "")),
                    "да" if record.get("has_deflection") else "нет",
                    format_diameter(float(record.get("deflection", 0.0) or 0.0)),
                    format_diameter(float(record.get("base_gap", 0.0) or 0.0)),
                    format_diameter(float(record.get("material_correction", 0.0) or 0.0)),
                    format_diameter(float(record.get("deflection_correction", 0.0) or 0.0)),
                    format_diameter(float(record.get("final_gap", 0.0) or 0.0)),
                    format_int(float(record.get("passes", 0) or 0)),
                    format_diameter(float(record.get("feed_speed", 0.0) or 0.0)),
                    str(record.get("risk_level", "")),
                    str(record.get("status", "")),
                    "да" if record.get("manual_override") else "нет",
                    str(record.get("manual_reason", "")),
                    "; ".join(str(item) for item in warnings),
                ]
            )
        return header, rows

    def machine_note(self, machine: MachineConfig) -> str:
        """Краткая справка о машине для окна «О системе»."""
        return (
            f"{machine.name}: диаметры {machine.min_diameter:g}–{machine.max_diameter:g} мм, "
            f"диапазон уставки {machine.min_gap:g}–{machine.max_gap:g} мм, "
            f"позиций валков {machine.roller_count}."
        )