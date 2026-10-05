"""Тесты расчётного ядра PipeAlign.

Тесты не зависят от PySide6 и Qt: проверяется чистая функция
``calculate_settings`` и связанные помощники.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Корень проекта добавляется в путь импорта, чтобы тесты запускались
# из любого каталога без установки пакета.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.calculator import (  # noqa: E402
    apply_manual_correction,
    calculate_settings,
    interpolate_curve,
)
from app.core.explanations import build_explanation  # noqa: E402
from app.core.validation import (  # noqa: E402
    WARNING_CONTROL_AFTER_FIRST_PASS,
    WARNING_DIAMETER_OUT_OF_RANGE,
    WARNING_THIN_WALL,
    validate_pipe,
)
from app.models.machine import MachineConfig  # noqa: E402
from app.models.pipe import Pipe  # noqa: E402

RECIPES_PATH = PROJECT_ROOT / "data" / "recipes.json"


def load_recipes() -> dict:
    """Загружает реальный файл рецептов, чтобы тесты проверяли боевые данные."""
    with RECIPES_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="module")
def recipes() -> dict:
    """Фикстура с содержимым recipes.json."""
    return load_recipes()


@pytest.fixture(scope="module")
def machine(recipes: dict) -> MachineConfig:
    """Фикстура с конфигурацией демо-машины."""
    return MachineConfig.from_dict(recipes["machine"])


def make_pipe(**overrides: object) -> Pipe:
    """Создаёт трубу с демонстрационными значениями по умолчанию."""
    defaults: dict[str, object] = {
        "order_no": "ТЕСТ-001",
        "batch": "T-001",
        "operator": "Тестов И.И.",
        "diameter": 57.0,
        "wall_thickness": 3.5,
        "material": "09Г2С",
        "length": 6000.0,
        "operation": "после гибки",
        "has_deflection": True,
        "deflection": 6.0,
        "required_straightness": 1.5,
    }
    defaults.update(overrides)
    return Pipe(**defaults)  # type: ignore[arg-type]


class TestDemoCase57x3_5:
    """Обязательный проверочный пример из технического задания."""

    def test_expected_values(self, machine: MachineConfig, recipes: dict) -> None:
        """Ключевые числа совпадают с эталонными значениями задания."""
        result = calculate_settings(make_pipe(), machine, recipes)

        assert result.base_gap == pytest.approx(29.8)
        assert result.material_correction == pytest.approx(0.3)
        assert result.deflection_correction == pytest.approx(0.6)
        assert result.operation_correction == pytest.approx(0.0)
        assert result.final_gap == pytest.approx(30.7)
        assert result.passes == 2
        assert result.feed_speed == pytest.approx(11.2)
        assert result.predicted_residual_curvature == pytest.approx(1.2)

    def test_risk_is_not_high(self, machine: MachineConfig, recipes: dict) -> None:
        """Риск демо-кейса не должен быть высоким."""
        result = calculate_settings(make_pipe(), machine, recipes)
        assert result.risk_level in {"низкий", "средний"}
        assert result.risk_level != "высокий"

    def test_control_after_first_pass_warning(self, machine: MachineConfig, recipes: dict) -> None:
        """При двух проходах выдаётся рекомендация контроля после первого."""
        result = calculate_settings(make_pipe(), machine, recipes)
        assert WARNING_CONTROL_AFTER_FIRST_PASS in result.warnings

    def test_explanation_mentions_all_terms(self, machine: MachineConfig, recipes: dict) -> None:
        """Объяснение содержит все слагаемые уставки."""
        result = calculate_settings(make_pipe(), machine, recipes)
        text = result.explanation

        assert "29.8" in text
        assert "0.3" in text
        assert "0.6" in text
        assert "30.7" in text
        assert "11.2" in text
        assert "Риск" in text

    def test_effect_estimate(self, machine: MachineConfig, recipes: dict) -> None:
        """Экономия времени и прогоны посчитаны по демо-нормам."""
        result = calculate_settings(make_pipe(), machine, recipes)

        assert result.as_is_time_minutes == pytest.approx(40.0)
        assert result.to_be_time_minutes == pytest.approx(15.0)
        assert result.time_saved_minutes == pytest.approx(25.0)
        assert result.as_is_trial_runs == 4
        assert result.to_be_trial_runs == 2
        assert result.to_be_defect_percent == pytest.approx(2.0)

    def test_result_is_valid(self, machine: MachineConfig, recipes: dict) -> None:
        """Диаметр 57 мм входит в диапазон машины, расчёт валиден."""
        result = calculate_settings(make_pipe(), machine, recipes)
        assert result.is_valid is True
        assert validate_pipe(make_pipe(), machine) == []


class TestWithoutDeflection:
    """Труба без остаточного изгиба."""

    def test_no_deflection_correction(self, machine: MachineConfig, recipes: dict) -> None:
        """Поправка на изгиб равна нулю, уставка равна базовой с материалом."""
        result = calculate_settings(
            make_pipe(has_deflection=False, deflection=0.0, operation="после механообработки"),
            machine,
            recipes,
        )
        assert result.deflection_correction == pytest.approx(0.0)
        assert result.final_gap == pytest.approx(29.8 + 0.3)
        assert result.passes == 1

    def test_single_pass_and_speed(self, machine: MachineConfig, recipes: dict) -> None:
        """Один проход и максимальная скорость подачи."""
        result = calculate_settings(
            make_pipe(has_deflection=False, deflection=0.0), machine, recipes
        )
        assert result.passes == 1
        assert result.feed_speed > 12.0

    def test_flag_disables_stored_deflection(self, machine: MachineConfig, recipes: dict) -> None:
        """Снятый флажок «есть изгиб» игнорирует значение поля."""
        pipe = make_pipe(has_deflection=False, deflection=12.0)
        assert pipe.effective_deflection == 0.0

        result = calculate_settings(pipe, machine, recipes)
        assert result.deflection_correction == pytest.approx(0.0)
        assert result.passes == 1

    def test_no_trial_runs_extra(self, machine: MachineConfig, recipes: dict) -> None:
        """Без изгиба достаточно одного пробного прогона."""
        result = calculate_settings(
            make_pipe(has_deflection=False, deflection=0.0), machine, recipes
        )
        assert result.to_be_trial_runs == 1
        assert result.to_be_time_minutes == pytest.approx(10.0)


class TestDiameterOutOfRange:
    """Диаметр за пределами рабочего диапазона машины."""

    def test_too_small_diameter(self, machine: MachineConfig, recipes: dict) -> None:
        """Диаметр 15 мм ниже минимума 20 мм — настройку применить нельзя."""
        pipe = make_pipe(diameter=15.0, wall_thickness=1.0, material="Ст20")
        result = calculate_settings(pipe, machine, recipes)

        assert result.is_valid is False
        assert WARNING_DIAMETER_OUT_OF_RANGE in result.warnings

    def test_too_large_diameter(self, machine: MachineConfig, recipes: dict) -> None:
        """Диаметр 120 мм выше максимума 89 мм — расчёт невалиден."""
        pipe = make_pipe(diameter=120.0, wall_thickness=6.0, material="Ст20")
        result = calculate_settings(pipe, machine, recipes)

        assert result.is_valid is False
        assert WARNING_DIAMETER_OUT_OF_RANGE in result.warnings

    def test_validation_reports_issue(self, machine: MachineConfig) -> None:
        """Валидация указывает проблемное поле."""
        issues = validate_pipe(make_pipe(diameter=10.0), machine)
        assert any(issue.field == "diameter" for issue in issues)

    def test_gap_still_bounded_by_machine(self, machine: MachineConfig, recipes: dict) -> None:
        """Даже для недопустимого диаметра уставка остаётся в диапазоне."""
        pipe = make_pipe(diameter=200.0, wall_thickness=8.0, material="Ст20")
        result = calculate_settings(pipe, machine, recipes)

        assert machine.min_gap <= result.final_gap <= machine.max_gap


class TestThinWall:
    """Тонкостенная труба."""

    def test_thin_wall_warns_and_adds_pass(self, machine: MachineConfig, recipes: dict) -> None:
        """Стенка 1.2 мм: предупреждение и минимум два прохода."""
        pipe = make_pipe(wall_thickness=1.2, has_deflection=False, deflection=0.0)
        result = calculate_settings(pipe, machine, recipes)

        assert WARNING_THIN_WALL in result.warnings
        assert result.passes == 2

    def test_thin_wall_reduces_speed(self, machine: MachineConfig, recipes: dict) -> None:
        """Скорость подачи ниже, чем у такой же толстостенной трубы."""
        thin = calculate_settings(make_pipe(wall_thickness=1.2), machine, recipes)
        thick = calculate_settings(make_pipe(wall_thickness=3.5), machine, recipes)

        assert thin.feed_speed < thick.feed_speed

    def test_thin_wall_raises_risk(self, machine: MachineConfig, recipes: dict) -> None:
        """Тонкостенность добавляет баллы к риску."""
        thin = calculate_settings(
            make_pipe(wall_thickness=1.2, deflection=0.0, has_deflection=False),
            machine,
            recipes,
        )
        thick = calculate_settings(
            make_pipe(wall_thickness=3.5, deflection=0.0, has_deflection=False),
            machine,
            recipes,
        )

        assert thin.risk_level != "низкий" or thin.passes >= thick.passes


class TestHighDeflection:
    """Большая стрела прогиба."""

    def test_three_passes(self, machine: MachineConfig, recipes: dict) -> None:
        """Изгиб 18 мм/м требует трёх проходов."""
        result = calculate_settings(
            make_pipe(deflection=18.0, operation="после гибки"), machine, recipes
        )
        assert result.passes == 3
        assert result.deflection_correction == pytest.approx(2.5)

    def test_high_deflection_speed_below_base(self, machine: MachineConfig, recipes: dict) -> None:
        """Скорость подачи снижается относительно базовой 14 м/мин."""
        result = calculate_settings(make_pipe(deflection=18.0), machine, recipes)
        assert result.feed_speed < 14.0
        assert result.feed_speed >= 6.0

    def test_curve_saturates_at_last_point(self, machine: MachineConfig, recipes: dict) -> None:
        """Изгиб выше последней точки кривой даёт максимальную компенсацию."""
        result = calculate_settings(
            make_pipe(diameter=57.0, deflection=45.0, operation="после гибки"),
            machine,
            recipes,
        )
        assert result.deflection_correction == pytest.approx(4.0)

    def test_curvature_forecast_exceeds_requirement(self, machine: MachineConfig, recipes: dict) -> None:
        """При большом изгибе и жёстком допуске прогноз превышает требование."""
        result = calculate_settings(
            make_pipe(
                deflection=30.0,
                required_straightness=0.5,
                operation="после гибки",
                material="12Х18Н10Т",
            ),
            machine,
            recipes,
        )
        assert result.predicted_residual_curvature > 0.5
        assert result.risk_level == "высокий"


class TestInterpolation:
    """Интерполяция по кривой зависимости."""

    def test_known_points(self) -> None:
        """В узлах кривой возвращается точное значение."""
        curve = [[0, 0.0], [2, 0.1], [4, 0.3], [6, 0.6]]
        assert interpolate_curve(curve, 0) == pytest.approx(0.0)
        assert interpolate_curve(curve, 2) == pytest.approx(0.1)
        assert interpolate_curve(curve, 6) == pytest.approx(0.6)

    def test_between_points(self) -> None:
        """Между узлами выполняется линейная интерполяция."""
        curve = [[0, 0.0], [4, 0.4], [8, 0.8]]
        assert interpolate_curve(curve, 2) == pytest.approx(0.2)
        assert interpolate_curve(curve, 6) == pytest.approx(0.6)

    def test_below_and_above_range(self) -> None:
        """За краями кривой возвращаются граничные значения."""
        curve = [[2, 0.1], [6, 0.6]]
        assert interpolate_curve(curve, 0) == pytest.approx(0.1)
        assert interpolate_curve(curve, 99) == pytest.approx(0.6)

    def test_empty_curve(self) -> None:
        """Пустая кривая даёт нулевую компенсацию."""
        assert interpolate_curve([], 5) == pytest.approx(0.0)


class TestRecipesData:
    """Проверки по данным demo_orders из recipes.json."""

    @pytest.mark.parametrize("order_no", ["ДЕМО-001", "ДЕМО-002", "ДЕМО-003"])
    def test_demo_orders_are_calculable(
        self, order_no: str, machine: MachineConfig, recipes: dict
    ) -> None:
        """Все демо-заказы рассчитываются и дают уставку в диапазоне машины."""
        from app.models.pipe import Pipe

        raw = next(item for item in recipes["demo_orders"] if item["order_no"] == order_no)
        result = calculate_settings(Pipe.from_dict(raw), machine, recipes)

        assert result.is_valid is True
        assert machine.min_gap <= result.final_gap <= machine.max_gap
        assert result.passes >= 1
        assert result.explanation

    def test_nearest_recipe_interpolation(
        self, machine: MachineConfig, recipes: dict
    ) -> None:
        """Для диаметра между рецептами уставка считается по ближайшему."""
        result = calculate_settings(
            make_pipe(
                diameter=52.0,
                wall_thickness=3.5,
                has_deflection=False,
                deflection=0.0,
                material="Ст20",
            ),
            machine,
            recipes,
        )
        # Ближайший рецепт Ø48: 24.8 + (52 − 48) × 0.5 = 26.8.
        assert result.base_gap == pytest.approx(26.8)
        assert result.final_gap == pytest.approx(26.8)


class TestManualCorrection:
    """Ручная коррекция уставки оператором."""

    def test_manual_override_applied(self, machine: MachineConfig, recipes: dict) -> None:
        """Уставка меняется, причина сохраняется, поправка в предупреждениях."""
        result = apply_manual_correction(
            make_pipe(), machine, recipes, 31.5, "подгонка по факту осмотра"
        )

        assert result.manual_override is True
        assert result.manual_reason == "подгонка по факту осмотра"
        assert result.final_gap == pytest.approx(31.5)
        assert "Настройка изменена вручную оператором." in result.warnings

    def test_manual_gap_is_clamped(self, machine: MachineConfig, recipes: dict) -> None:
        """Ручное значение ограничивается диапазоном машины."""
        result = apply_manual_correction(make_pipe(), machine, recipes, 500.0, "ошибка ввода")
        assert result.final_gap == pytest.approx(machine.max_gap)

    def test_manual_correction_adds_time(self, machine: MachineConfig, recipes: dict) -> None:
        """Ручная коррекция увеличивает время переналадки на 2 минуты."""
        auto = calculate_settings(make_pipe(), machine, recipes)
        manual = apply_manual_correction(make_pipe(), machine, recipes, 31.5, "коррекция")

        assert manual.to_be_time_minutes == pytest.approx(
            auto.to_be_time_minutes + 2.0
        )


class TestExplanationBuilder:
    """Текстовое обоснование."""

    def test_text_without_deflection(self, machine: MachineConfig, recipes: dict) -> None:
        """Без изгиба текст сообщает, что компенсация не применялась."""
        pipe = make_pipe(has_deflection=False, deflection=0.0)
        result = calculate_settings(pipe, machine, recipes)
        text = build_explanation(pipe, machine, result)

        assert "компенсация не применялась" in text
        assert "не изменяет числовую уставку" in text