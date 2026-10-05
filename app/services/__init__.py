"""Работа с данными: рецепты, журнал, отчёты."""

from __future__ import annotations

__all__ = ["RecipeRepository", "JournalService", "ReportService"]


def __getattr__(name: str) -> type:  # pragma: no cover - ленивый реэкспорт
    """Ленивый реэкспорт, чтобы не тянуть Qt при импорте core."""
    if name == "RecipeRepository":
        from app.services.recipe_repository import RecipeRepository

        return RecipeRepository
    if name == "JournalService":
        from app.services.journal_service import JournalService

        return JournalService
    if name == "ReportService":
        from app.services.report_service import ReportService

        return ReportService
    raise AttributeError(name)