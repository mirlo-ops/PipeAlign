"""Расчётное ядро: чистые функции без Qt."""

from __future__ import annotations

from app.core.calculator import (
    calculate_settings,
    interpolate_curve,
    nearest_recipe,
    resolve_material,
)
from app.core.explanations import build_explanation, format_signed
from app.core.validation import (
    ValidationIssue,
    validate_pipe,
    pipe_to_text,
)

__all__ = [
    "calculate_settings",
    "interpolate_curve",
    "nearest_recipe",
    "resolve_material",
    "build_explanation",
    "format_signed",
    "ValidationIssue",
    "validate_pipe",
    "pipe_to_text",
]