"""Форматирование чисел и дат под русскую локаль.

В интерфейсе и отчётах используется запятая как десятичный разделитель,
поскольку это принято в русскоязычной производственной документации.
"""

from __future__ import annotations

from datetime import datetime

#: Разделитель целой и дробной части, принятый в UI.
DECIMAL_SEPARATOR = ","

TIMESTAMP_FORMAT = "%d.%m.%Y %H:%M:%S"


def _number(value: float, decimals: int) -> str:
    """Форматирует число с запятой вместо точки."""
    return f"{value:.{decimals}f}".replace(".", DECIMAL_SEPARATOR)


def format_mm(value: float) -> str:
    """Миллиметры с одним знаком: ``30,7 мм``."""
    return f"{_number(value, 1)} мм"


def format_mm_per_m(value: float) -> str:
    """Кривизна в мм/м: ``1,2 мм/м``."""
    return f"{_number(value, 1)} мм/м"


def format_m_per_min(value: float) -> str:
    """Скорость подачи: ``11,2 м/мин``."""
    return f"{_number(value, 1)} м/мин"


def format_minutes(value: float) -> str:
    """Время в минутах: ``25,0 мин``."""
    return f"{_number(value, 1)} мин"


def format_percent(value: float) -> str:
    """Процент без знака «%» у вставленных значений: ``6,0``."""
    return _number(value, 1)


def format_percent_text(value: float) -> str:
    """Процент со знаком: ``6,0 %``."""
    return f"{_number(value, 1)} %"


def format_int(value: int) -> str:
    """Целое число без дробной части."""
    return str(int(round(value)))


def format_diameter(value: float) -> str:
    """Диаметр для таблиц: ``57,0``."""
    return _number(value, 1)


def format_timestamp(iso_text: str) -> str:
    """Преобразует ISO-время журнала в читаемый локальный вид.

    Некорректная строка возвращается как есть, чтобы таблица не падала.
    """
    try:
        parsed = datetime.fromisoformat(iso_text)
    except (TypeError, ValueError):
        return iso_text
    return parsed.strftime(TIMESTAMP_FORMAT)


def now_iso() -> str:
    """Текущее время в формате ISO 8601 для записи в журнал."""
    return datetime.now().isoformat(timespec="seconds")


def format_length_mm(value: float) -> str:
    """Длина трубы: ``6000 мм``."""
    return f"{format_int(value)} мм"


def format_length_m(value: float) -> str:
    """Длина трубы в метрах: ``6 м``."""
    return f"{_number(value / 1000.0, 2)} м"