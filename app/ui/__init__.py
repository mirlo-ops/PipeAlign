"""Интерфейс PipeAlign на PySide6 / QtWidgets."""

from __future__ import annotations

from app.ui.about_tab import AboutTab
from app.ui.dialogs import (
    DemoOrderDialog,
    ExplanationDialog,
    ManualCorrectionDialog,
    OperatorMistakeDialog,
    PipePresetDialog,
)
from app.ui.input_panel import InputPanel
from app.ui.journal_tab import JournalTab
from app.ui.machine_view import MachineView
from app.ui.main_window import MainWindow
from app.ui.report_tab import ReportTab
from app.ui.result_panel import ResultPanel

__all__ = [
    "MainWindow",
    "InputPanel",
    "MachineView",
    "ResultPanel",
    "ReportTab",
    "JournalTab",
    "AboutTab",
    "ExplanationDialog",
    "ManualCorrectionDialog",
    "DemoOrderDialog",
    "PipePresetDialog",
    "OperatorMistakeDialog",
]