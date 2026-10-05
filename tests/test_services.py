"""Тесты сервисов: журнал, рецепты, отчёты.

Проверяется работа с файлами во временном каталоге, включая
восстановление повреждённого журнала. Qt не используется.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.calculator import calculate_settings  # noqa: E402
from app.models.machine import MachineConfig  # noqa: E402
from app.models.pipe import Pipe  # noqa: E402
from app.services.journal_service import (  # noqa: E402
    BACKUP_JOURNAL_NAME,
    STATUS_APPLIED,
    STATUS_CALCULATED,
    STATUS_MANUAL,
    JournalService,
)
from app.services.recipe_repository import RecipeError, RecipeRepository  # noqa: E402
from app.services.report_service import (  # noqa: E402
    build_report_text,
    build_summary,
    comparison_rows,
    estimate_operator_mistake,
    report_csv,
    write_csv,
)

RECIPES_PATH = PROJECT_ROOT / "data" / "recipes.json"


@pytest.fixture()
def repository() -> RecipeRepository:
    """Репозиторий с реальным файлом рецептов."""
    return RecipeRepository(RECIPES_PATH)


@pytest.fixture()
def pipe() -> Pipe:
    """Демонстрационная труба ДЕМО-002."""
    return Pipe(
        order_no="ДЕМО-002",
        batch="B-204",
        operator="Петров П.П.",
        diameter=57.0,
        wall_thickness=3.5,
        material="09Г2С",
        length=6000.0,
        operation="после гибки",
        has_deflection=True,
        deflection=6.0,
        required_straightness=1.5,
    )


@pytest.fixture()
def journal(tmp_path: Path) -> JournalService:
    """Журнал во временном каталоге."""
    return JournalService(tmp_path / "journal.json")


class TestRecipeRepository:
    """Загрузка и проверка файла рецептов."""

    def test_loads_machine_config(self, repository: RecipeRepository) -> None:
        """Конфигурация машины соответствует заданию."""
        machine = repository.machine
        assert machine.name.startswith("Косовалковая")
        assert machine.min_diameter == 20
        assert machine.max_diameter == 89
        assert machine.min_gap == 10
        assert machine.max_gap == 50
        assert machine.roller_count == 3

    def test_lists_materials_and_operations(self, repository: RecipeRepository) -> None:
        """Справочники марок и операций загружаются."""
        assert "09Г2С" in repository.materials
        assert "после гибки" in repository.operations
        assert len(repository.operations) == 4

    def test_demo_orders_parsed(self, repository: RecipeRepository) -> None:
        """Демо-заказы преобразуются в объекты Pipe."""
        orders = repository.demo_orders
        assert len(orders) == 3
        assert orders[1].order_no == "ДЕМО-002"
        assert orders[1].wall_thickness == 3.5
        assert orders[1].has_deflection is True

    def test_default_demo_order(self, repository: RecipeRepository) -> None:
        """Демо-кейс по умолчанию — ДЕМО-002."""
        assert repository.default_demo_order().order_no == "ДЕМО-002"

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        """Отсутствующий файл даёт понятную ошибку, а не исключение Qt."""
        repository = RecipeRepository(tmp_path / "нет.json")
        with pytest.raises(RecipeError, match="не найден"):
            _ = repository.raw

    def test_broken_json_raises(self, tmp_path: Path) -> None:
        """Повреждённый JSON распознаётся."""
        path = tmp_path / "recipes.json"
        path.write_text("{ это не json", encoding="utf-8")
        repository = RecipeRepository(path)
        with pytest.raises(RecipeError, match="повреждён"):
            _ = repository.raw

    def test_missing_section_raises(self, tmp_path: Path) -> None:
        """Файл без обязательных секций отклоняется."""
        path = tmp_path / "recipes.json"
        path.write_text(json.dumps({"machine": {}}), encoding="utf-8")
        repository = RecipeRepository(path)
        with pytest.raises(RecipeError, match="отсутствуют разделы"):
            _ = repository.raw


class TestJournalService:
    """Запись, чтение, фильтрация и восстановление журнала."""

    def test_empty_journal_on_first_run(self, journal: JournalService) -> None:
        """Новый журнал пуст, файл не создаётся до первой записи."""
        assert journal.load() == []

    def test_add_entry_creates_file(
        self, journal: JournalService, repository: RecipeRepository, pipe: Pipe
    ) -> None:
        """Запись сохраняется в файл и читается обратно."""
        machine = repository.machine
        result = calculate_settings(pipe, machine, repository.raw)
        journal.add_entry(pipe, result, STATUS_CALCULATED)

        records = journal.load()
        assert len(records) == 1
        assert records[0]["order_no"] == "ДЕМО-002"
        assert records[0]["status"] == STATUS_CALCULATED
        assert records[0]["final_gap"] == pytest.approx(30.7)
        assert "timestamp" in records[0]

    def test_statuses_are_preserved(
        self, journal: JournalService, repository: RecipeRepository, pipe: Pipe
    ) -> None:
        """Все статусы сохраняются без изменений."""
        result = calculate_settings(pipe, repository.machine, repository.raw)
        for status in (STATUS_CALCULATED, STATUS_APPLIED, STATUS_MANUAL):
            journal.add_entry(pipe, result, status)
        statuses = [record["status"] for record in journal.load()]
        assert statuses == [STATUS_CALCULATED, STATUS_APPLIED, STATUS_MANUAL]

    def test_persistence_between_instances(
        self, journal: JournalService, repository: RecipeRepository, pipe: Pipe
    ) -> None:
        """Данные читаются новым экземпляром сервиса — как после перезапуска."""
        result = calculate_settings(pipe, repository.machine, repository.raw)
        journal.add_entry(pipe, result, STATUS_APPLIED)

        reopened = JournalService(journal.path)
        assert len(reopened.load()) == 1

    def test_broken_journal_is_quarantined(
        self, journal: JournalService
    ) -> None:
        """Повреждённый журнал переносится в journal.bad.json, приложение живёт."""
        journal.path.parent.mkdir(parents=True, exist_ok=True)
        journal.path.write_text("{{{ сломанный json", encoding="utf-8")

        records = journal.load()
        assert records == []
        assert (journal.path.parent / "journal.bad.json").exists()
        assert journal.startup_warnings
        assert journal.load() == []

    def test_journal_with_wrong_structure_recovered(
        self, journal: JournalService
    ) -> None:
        """Объект вместо списка записей также восстанавливается."""
        journal.path.parent.mkdir(parents=True, exist_ok=True)
        journal.path.write_text('{"это": "не список"}', encoding="utf-8")

        assert journal.load() == []
        assert (journal.path.parent / "journal.bad.json").exists()

    def test_clear_creates_backup(
        self, journal: JournalService, repository: RecipeRepository, pipe: Pipe
    ) -> None:
        """Очистка создаёт резервную копию и пустой журнал."""
        result = calculate_settings(pipe, repository.machine, repository.raw)
        journal.add_entry(pipe, result, STATUS_APPLIED)

        success, message = journal.clear()
        assert success is True
        assert BACKUP_JOURNAL_NAME in message
        assert journal.load() == []
        assert (journal.path.parent / BACKUP_JOURNAL_NAME).exists()

    def test_filter_by_order_and_operator(
        self, journal: JournalService, repository: RecipeRepository, pipe: Pipe
    ) -> None:
        """Фильтр работает по номеру заказа и по оператору."""
        result = calculate_settings(pipe, repository.machine, repository.raw)
        journal.add_entry(pipe, result, STATUS_APPLIED)
        journal.add_entry(
            pipe.copy(order_no="ДЕМО-009", operator="Сидоров С.С."),
            result,
            STATUS_APPLIED,
        )

        assert len(journal.filter_records(journal.load(), "ДЕМО-002")) == 1
        assert len(journal.filter_records(journal.load(), "Сидоров")) == 1
        assert len(journal.filter_records(journal.load(), "нетакого")) == 0
        assert len(journal.filter_records(journal.load(), "")) == 2

    def test_aggregates(
        self, journal: JournalService, repository: RecipeRepository, pipe: Pipe
    ) -> None:
        """Агрегаты считают экономию, коррекции и высокий риск."""
        machine = repository.machine
        result = calculate_settings(pipe, machine, repository.raw)
        journal.add_entry(pipe, result, STATUS_APPLIED)
        journal.add_entry(pipe, result, STATUS_MANUAL)

        aggregates = journal.aggregates(journal.load())
        assert aggregates["total"] == 2
        assert aggregates["applied"] == 1
        assert aggregates["saved_total"] == pytest.approx(50.0)
        assert aggregates["saved_average"] == pytest.approx(25.0)
        assert aggregates["manual_overrides"] == 0
        assert aggregates["high_risk"] == 0

    def test_rows_for_table_has_all_columns(
        self, journal: JournalService, repository: RecipeRepository, pipe: Pipe
    ) -> None:
        """Таблица журнала содержит все колонки."""
        from app.services.journal_service import COLUMNS

        result = calculate_settings(pipe, repository.machine, repository.raw)
        journal.add_entry(pipe, result, STATUS_APPLIED)
        rows = journal.rows_for_table(journal.load())

        assert len(rows) == 1
        assert len(rows[0]) == len(COLUMNS)

    def test_csv_has_bom_and_semicolon(
        self, journal: JournalService, repository: RecipeRepository, pipe: Pipe
    ) -> None:
        """CSV пишется в utf-8-sig с разделителем «;»."""
        result = calculate_settings(pipe, repository.machine, repository.raw)
        journal.add_entry(pipe, result, STATUS_APPLIED)
        header, rows = journal.csv_rows(journal.load())
        target = write_csv(journal.path.parent / "export.csv", header, rows)

        raw = target.read_bytes()
        assert raw.startswith(b"\xef\xbb\xbf")
        with target.open("r", encoding="utf-8-sig", newline="") as handle:
            parsed = list(csv.reader(handle, delimiter=";"))
        assert parsed[0][0] == "Время"
        assert "ДЕМО-002" in parsed[1]


class TestReportService:
    """Отчёты и оценка ошибки наладчика."""

    def test_comparison_rows_count(
        self, repository: RecipeRepository, pipe: Pipe
    ) -> None:
        """Сравнение содержит все требуемые показатели."""
        result = calculate_settings(pipe, repository.machine, repository.raw)
        rows = comparison_rows(result)
        titles = [row[0] for row in rows]

        assert "Время переналадки" in titles
        assert "Пробные прогоны" in titles
        assert "Брак по кривизне" in titles
        assert "Зависимость от оператора" in titles
        assert "Прослеживаемость настроек" in titles
        assert "Обучение нового оператора" in titles

    def test_summary_values(
        self, repository: RecipeRepository, pipe: Pipe
    ) -> None:
        """Сводка содержит форматированные ключевые метрики."""
        result = calculate_settings(pipe, repository.machine, repository.raw)
        summary = build_summary(result, pipe, repository.machine)

        assert summary["final_gap"] == "30,7 мм"
        assert summary["time_saved_value"] == pytest.approx(25.0)
        assert summary["risk"] == "низкий"
        assert summary["defect_to_be"] == "2,0 %"

    def test_report_text_contains_formula_and_disclaimer(
        self, repository: RecipeRepository, pipe: Pipe
    ) -> None:
        """Текстовый отчёт содержит формулу и дисклеймер."""
        result = calculate_settings(pipe, repository.machine, repository.raw)
        text = build_report_text(result, pipe, repository.machine)

        assert "Итоговая уставка" in text
        assert "Демонстрационный прототип" in text
        assert "АГРЕГИРОВАННЫЕ ДАННЫЕ ЖУРНАЛА" in text

    def test_report_csv_export(
        self, tmp_path: Path, repository: RecipeRepository, pipe: Pipe
    ) -> None:
        """Отчёт выгружается в CSV с русскими заголовками."""
        result = calculate_settings(pipe, repository.machine, repository.raw)
        target = report_csv(
            tmp_path / "report.csv", result, pipe, repository.machine
        )

        with target.open("r", encoding="utf-8-sig", newline="") as handle:
            parsed = list(csv.reader(handle, delimiter=";"))
        assert parsed[0] == ["Раздел", "Показатель", "Значение"]
        assert any(row[1] == "Итоговая уставка" for row in parsed[1:])

    def test_operator_mistake_too_small_gap(
        self, repository: RecipeRepository, pipe: Pipe
    ) -> None:
        """Оставленная малая уставка трактуется как риск завала валков."""
        result = calculate_settings(pipe, repository.machine, repository.raw)
        estimate = estimate_operator_mistake(result, stale_gap=20.0)

        assert estimate["delta"] == pytest.approx(10.7)
        assert estimate["severity"] == "высокий"
        assert estimate["defect_percent"] > result.to_be_defect_percent
        assert "завал" in estimate["verdict"]

    def test_operator_mistake_too_large_gap(
        self, repository: RecipeRepository, pipe: Pipe
    ) -> None:
        """Оставленная большая уставка даёт остаточную кривизну."""
        result = calculate_settings(pipe, repository.machine, repository.raw)
        estimate = estimate_operator_mistake(result, stale_gap=45.0)

        assert estimate["delta"] == pytest.approx(-14.3)
        assert estimate["severity"] == "высокий"
        assert "кривизна" in estimate["verdict"]

    def test_operator_mistake_matching_gap(
        self, repository: RecipeRepository, pipe: Pipe
    ) -> None:
        """При совпадении уставок риск оценивается как низкий."""
        result = calculate_settings(pipe, repository.machine, repository.raw)
        estimate = estimate_operator_mistake(result, stale_gap=result.final_gap)

        assert estimate["severity"] == "низкий"
        assert estimate["extra_time"] == 0.0