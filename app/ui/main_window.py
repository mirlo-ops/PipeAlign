"""Главное окно приложения: вкладки, демо-сценарий, журнал сессии."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app import DISCLAIMER
from app.core import validation as v
from app.core.calculator import apply_manual_correction, calculate_settings
from app.core.validation import pipe_to_text, validate_pipe
from app.models.machine import MachineConfig
from app.models.pipe import Pipe
from app.models.result import CalculationResult
from app.services.auth_service import Session
from app.services.journal_service import (
    STATUS_APPLIED,
    STATUS_CALCULATED,
    STATUS_CANCELLED,
    STATUS_MANUAL,
    JournalService,
)
from app.services.recipe_repository import RecipeRepository
from app.ui.about_tab import AboutTab
from app.ui.dialogs import (
    DemoOrderDialog,
    ExplanationDialog,
    ManualCorrectionDialog,
    OperatorMistakeDialog,
    PipePresetDialog,
    confirm,
    show_critical,
    show_warning,
)
from app.ui.input_panel import InputPanel
from app.ui.journal_tab import JournalTab
from app.ui.labels import ElidedLabel
from app.ui.machine_view import (
    STATUS_CALCULATED as SCHEMA_CALCULATED,
    MachineView,
)
from app.ui.report_tab import ReportTab
from app.ui.result_panel import ResultPanel
from app.utils.formatting import format_mm

#: Заголовок главного окна.
WINDOW_TITLE = (
    "ТрубоНастрой — демонстрационный ассистент переналадки "
    "косовалковой правильной машины"
)

#: Индексы вкладок.
TAB_SETUP = 0
TAB_REPORT = 1
TAB_JOURNAL = 2
TAB_ABOUT = 3

#: Сообщение при изменении параметров после расчёта.
STATUS_STALE = "Параметры изменены, требуется перерасчёт"

#: Стандартное состояние после расчёта.
STATUS_CALCULATED_READY = "Расчёт выполнен, настройка готова к применению"


class MainWindow(QMainWindow):
    """Координирует вкладки, расчёт, применение настройки и журнал сессии.

    Главное окно намеренно «толстое»: все слоты обёрнуты защитой от
    непредвиденных исключений, чтобы демонстрация не прерывалась.
    """

    #: Запрос на выход из учётной записи. Главное окно само ничего не
    #: открывает: новую сессию создаёт `main.py`, поэтому смена
    #: пользователя и пересборка окна живут в одном месте.
    logoutRequested = Signal()

    def __init__(
        self,
        repository: RecipeRepository,
        journal: JournalService,
        session: Session,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._repository = repository
        self._journal = journal
        self._machine: MachineConfig = repository.machine
        self._session = session

        self._pipe: Pipe | None = None
        self._result: CalculationResult | None = None
        self._is_result_current = False
        self._is_applied = False
        self._scenario_running = False
        self._scenario_timers: list[QTimer] = []

        self.setWindowTitle(WINDOW_TITLE)
        self.setMinimumSize(1280, 720)
        self.resize(1500, 900)

        self._build_central_widget()
        self._build_status_bar()
        self._build_menu()
        self._connect_signals()
        self._startup_checks()

    # ------------------------------------------------------------------
    # Построение интерфейса
    # ------------------------------------------------------------------

    def _build_central_widget(self) -> None:
        """Создаёт вкладки и центральный виджет."""
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 6)
        layout.setSpacing(8)

        layout.addWidget(self._build_banner())

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(False)

        self.input_panel = InputPanel(
            self._machine,
            self._repository.materials,
            self._repository.operations,
        )
        self.machine_view = MachineView(self._machine)
        self.result_panel = ResultPanel(self._machine)
        self.report_tab = ReportTab(self._machine, self._journal)
        self.journal_tab = JournalTab(self._journal)
        self.about_tab = AboutTab(self._machine, self._journal)

        self.tabs.addTab(self._build_setup_tab(), "Переналадка")
        self.tabs.addTab(self.report_tab, "Отчёт")
        self.tabs.addTab(self.journal_tab, "Журнал")
        self.tabs.addTab(self.about_tab, "О системе")

        layout.addWidget(self.tabs, 1)
        layout.addWidget(self._build_session_log())
        self.setCentralWidget(central)

    def _build_banner(self) -> QLabel:
        """Постоянный дисклеймер над вкладками."""
        banner = QLabel(DISCLAIMER)
        banner.setObjectName("Disclaimer")
        banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        banner.setWordWrap(True)
        return banner

    def _build_setup_tab(self) -> QWidget:
        """Вкладка «Переналадка»: форма, схема, результаты, лог событий."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 8, 6, 6)
        layout.setSpacing(8)

        # Права роли применяются до сборки вкладок: панели скрываются
        # до того, как попадут в сплиттер, поэтому вёрстка сразу
        # учитывает то, какие блоки доступны сотруднику.
        self.input_panel.apply_role(self._session)
        self.result_panel.apply_role(self._session)

        top_splitter = QSplitter(Qt.Orientation.Horizontal)
        top_splitter.setChildrenCollapsible(False)
        top_splitter.addWidget(self.input_panel)
        top_splitter.addWidget(self._wrap_visualization())
        top_splitter.addWidget(self.result_panel)
        top_splitter.setStretchFactor(0, 0)
        top_splitter.setStretchFactor(1, 1)
        top_splitter.setStretchFactor(2, 0)
        top_splitter.setSizes([390, 640, 420])
        layout.addWidget(top_splitter, 1)

        return page

    def _wrap_visualization(self) -> QWidget:
        """Оборачивает схему машины в групповую рамку."""
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(6, 0, 6, 0)
        layout.setSpacing(6)

        title = QLabel("Схема правильной машины")
        title.setObjectName("SectionTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        layout.addWidget(self.machine_view, 1)

        hint = QLabel(
            "После расчёта валки перемещаются к целевой уставке. "
            "Оранжевый цвет — предпросмотр, зелёный — настройка применена."
        )
        hint.setObjectName("HintLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        return box

    def _build_session_log(self) -> QWidget:
        """Нижний журнал событий текущей сессии."""
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(6, 0, 6, 0)
        layout.setSpacing(4)

        title = QLabel("Журнал событий текущей сессии")
        title.setObjectName("FieldLabel")
        layout.addWidget(title)

        self.session_log = QPlainTextEdit()
        self.session_log.setReadOnly(True)
        self.session_log.setMaximumBlockCount(400)
        self.session_log.setMaximumHeight(112)
        self.session_log.setPlaceholderText(
            "Здесь появляются события: загрузка заказа, расчёт, "
            "перемещение валков, применение настройки, запись в журнал."
        )
        layout.addWidget(self.session_log)
        return box

    def _build_status_bar(self) -> None:
        """Строка состояния: кто вошёл, роль, выход и текущий статус."""
        status = self.statusBar()

        # ФИО и роль держим перед именем машины: сотрудник должен видеть,
        # под каким доступом он работает, иначе права незаметны.
        self.user_label = QLabel(self._session_badge_text())
        self.user_label.setObjectName("UserBadge")
        self.user_label.setToolTip(f"Вход выполнен: {self._session.login_time}")
        # Метка сотрудника не сокращается: под кем идёт работа важнее
        # имени машины, поэтому при нехватке места ужимаются соседи.
        self.user_label.setMinimumWidth(
            self.user_label.fontMetrics().horizontalAdvance(
                self.user_label.text()
            )
        )
        status.addPermanentWidget(self.user_label)

        # Выход стоит сразу рядом с именем: вход и выход должны быть
        # на одном экране, иначе смена сотрудника ищется по меню.
        self.logout_button = QPushButton("Сменить пользователя")
        self.logout_button.setObjectName("LogoutButton")
        self.logout_button.setToolTip(
            "Выйти из учётной записи и войти заново"
        )
        self.logout_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.logout_button.clicked.connect(
            self._guard(self._on_logout)
        )
        status.addPermanentWidget(self.logout_button)

        self.machine_label = ElidedLabel(self._machine.name)
        # Имя машины уступает место статусу: какая машина стоит в
        # наряде, известно и так, а что происходит прямо сейчас — нет.
        self.machine_label.setMinimumWidth(60)
        self.machine_label.setMaximumWidth(280)
        status.addPermanentWidget(self.machine_label)

        self.status_label = ElidedLabel("Готово к работе")
        self.status_label.setMinimumWidth(160)
        status.addWidget(self.status_label)

    def _session_badge_text(self) -> str:
        """Текст метки сотрудника в строке состояния.

        Время входа в подпись не входит: строка состояния уже занята
        именем машины и кнопкой выхода, и длинная подпись обрезается при
        минимальной ширине окна. Оно доступно в подсказке.
        """
        return f"{self._session.operator_name} · {self._session.role_title}"

    def _build_menu(self) -> None:
        """Меню приложения: повтор расчёта и выход."""
        file_menu = self.menuBar().addMenu("&Программа")

        recalc_action = QAction("&Рассчитать настройку", self)
        recalc_action.setShortcut("Ctrl+R")
        recalc_action.triggered.connect(self._guard(self._on_calculate))
        file_menu.addAction(recalc_action)

        scenario_action = QAction("Демо-&сценарий", self)
        scenario_action.setShortcut("Ctrl+D")
        scenario_action.triggered.connect(self._guard(self._on_demo_scenario))
        file_menu.addAction(scenario_action)

        refresh_action = QAction("Обновить &журнал", self)
        refresh_action.setShortcut("Ctrl+J")
        refresh_action.triggered.connect(self._guard(self._on_refresh_journal))
        file_menu.addAction(refresh_action)

        file_menu.addSeparator()

        logout_action = QAction("&Сменить пользователя", self)
        logout_action.setShortcut("Ctrl+L")
        logout_action.setStatusTip("Выйти из учётной записи и войти заново")
        logout_action.triggered.connect(self._guard(self._on_logout))
        file_menu.addAction(logout_action)

        exit_action = QAction("&Выход", self)
        exit_action.setShortcut("Alt+F4")
        exit_action.setStatusTip("Закрыть программу")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        help_menu = self.menuBar().addMenu("&Справка")
        about_action = QAction("&О системе", self)
        about_action.setShortcut("F1")
        about_action.triggered.connect(self._go_to_about)
        help_menu.addAction(about_action)

        disclaimer_action = QAction("Демо-дисклеймер", self)
        disclaimer_action.triggered.connect(
            lambda: show_warning(self, "Демонстрационный прототип", DISCLAIMER)
        )
        help_menu.addAction(disclaimer_action)

    def _connect_signals(self) -> None:
        """Подключает сигналы панелей к слотам главного окна."""
        self.input_panel.parametersChanged.connect(
            self._guard(self._on_parameters_changed)
        )
        self.input_panel.calculateRequested.connect(self._guard(self._on_calculate))
        self.input_panel.applyRequested.connect(self._guard(self._on_apply))
        self.input_panel.manualRequested.connect(self._guard(self._on_manual))
        self.input_panel.resetRequested.connect(self._guard(self._on_reset))
        self.input_panel.demoOrderRequested.connect(self._guard(self._on_load_demo_order))
        self.input_panel.demoScenarioRequested.connect(
            self._guard(self._on_demo_scenario)
        )
        self.input_panel.presetRequested.connect(self._guard(self._on_preset))
        self.input_panel.mistakeSimulationRequested.connect(
            self._guard(self._on_mistake_simulation)
        )
        self.input_panel.explanationRequested.connect(
            self._guard(self._on_show_explanation)
        )
        self.result_panel.explanationRequested.connect(
            self._guard(self._on_show_explanation)
        )
        self.machine_view.animationFinished.connect(
            self._on_animation_finished
        )
        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _startup_checks(self) -> None:
        """Первичная инициализация формы и журнала."""
        self.input_panel.fill_from_pipe(self.input_panel.collect())
        self._pipe = self.input_panel.collect()
        self.machine_view.set_pipe_diameter(self._pipe.diameter)
        self._invalidate_result("Готово к работе")

        for warning in self._journal.startup_warnings:
            self._log_event(f"ВНИМАНИЕ: {warning}")
        if self._journal.startup_warnings:
            show_warning(
                self,
                "Журнал переналадок восстановлен",
                self._journal.startup_warnings[0],
            )
        else:
            self._log_event(f"Журнал: {self._journal.path}")

    # ------------------------------------------------------------------
    # Защита слотов
    # ------------------------------------------------------------------

    def _guard(self, handler: Any) -> Any:
        """Оборачивает слот так, чтобы исключение не убивало приложение."""

        def wrapper(*args: Any) -> None:
            try:
                handler(*args)
            except Exception as exc:  # noqa: BLE001 - демо должно быть устойчивым
                self._log_event(f"ОШИБКА: {exc}")
                show_critical(
                    self,
                    "Непредвиденная ошибка",
                    "Действие не выполнено из-за внутренней ошибки приложения.\n"
                    f"Текст ошибки: {exc}\n\n"
                    "Данные журнала сохранены. Попробуйте повторить действие.",
                )
                self.status_label.setText("Ошибка выполнения действия")

        return wrapper

    # ------------------------------------------------------------------
    # Журнал сессии и статус
    # ------------------------------------------------------------------

    def _log_event(self, message: str) -> None:
        """Добавляет строку в журнал событий сессии."""
        from app.utils.formatting import now_iso

        self.session_log.appendPlainText(f"[{now_iso()}] {message}")

    def _set_status(self, text: str) -> None:
        """Обновляет строку состояния."""
        self.status_label.setText(text)

    def _invalidate_result(self, status: str) -> None:
        """Снимает актуальность расчёта и блокирует применение."""
        self._is_result_current = False
        self.input_panel.set_apply_enabled(False)
        self.input_panel.set_manual_enabled(False)
        self._set_status(status)

    # ------------------------------------------------------------------
    # Действия расчёта
    # ------------------------------------------------------------------

    def _on_parameters_changed(self) -> None:
        """Снимает актуальность результата при изменении параметров."""
        self._pipe = self.input_panel.collect()
        self.machine_view.set_pipe_diameter(self._pipe.diameter)
        if self._is_result_current or self._result is not None:
            self._invalidate_result(STATUS_STALE)
            self._log_event("Параметры изменены, результат расчёта снят")
            self.machine_view.mark_waiting()
            self._is_applied = False
        else:
            self._set_status("Готово к работе")

    def _on_calculate(self) -> None:
        """Выполняет расчёт и включает предпросмотр перемещения валков."""
        pipe = self.input_panel.collect()
        self._pipe = pipe
        self.machine_view.set_pipe_diameter(pipe.diameter)

        issues = validate_pipe(pipe, self._machine)
        if issues:
            message = "; ".join(issue.message for issue in issues)
            self._log_event(f"Расчёт не выполнен: {message}")
            self._invalidate_result("Ошибка параметров")
            self.result_panel.clear()
            self.machine_view.mark_error("проверьте параметры")
            show_warning(self, "Параметры заполнены неверно", message)
            return

        result = calculate_settings(pipe, self._machine, self._repository.raw)
        self._result = result
        self._is_applied = False
        self._is_result_current = True

        self.result_panel.show_result(result, pipe.required_straightness)
        self.input_panel.set_apply_enabled(result.is_valid)
        self.input_panel.set_manual_enabled(result.is_valid)
        self.result_panel.set_explanation_enabled(True)

        self._journal.add_entry(pipe, result, STATUS_CALCULATED, "Расчёт выполнен")
        self._log_event(f"Выполнен расчёт: итоговая уставка {format_mm(result.final_gap)}")
        self._log_event(pipe_to_text(pipe))
        self._log_event(f"Запись добавлена в журнал ({STATUS_CALCULATED})")

        if result.is_valid:
            self.machine_view.preview_to(result.final_gap, SCHEMA_CALCULATED)
            self._set_status(STATUS_CALCULATED_READY)
        else:
            self.machine_view.mark_error("диаметр вне диапазона машины")
            self._set_status("Расчёт невалиден: диаметр вне диапазона машины")

    def _on_animation_finished(self) -> None:
        """Фиксирует завершение предпросмотра."""
        if self._result is None:
            return
        self._log_event(
            f"Валки перемещены в предпросмотре: {format_mm(self._result.final_gap)}"
        )

    def _on_apply(self) -> None:
        """Применяет настройку и пишет запись в журнал."""
        if self._result is None or not self._is_result_current:
            show_warning(
                self,
                "Нечего применять",
                "Сначала выполните расчёт настройки.",
            )
            return
        if not self._result.is_valid:
            show_warning(
                self,
                "Настройку применить нельзя",
                "Расчёт невалиден: проверьте параметры трубы.",
            )
            return

        pipe = self.input_panel.collect()
        critical = v.critical_warnings(self._result.warnings)
        needs_confirmation = self._result.is_high_risk or bool(critical)
        if needs_confirmation:
            details = "\n".join(f"• {item}" for item in critical)
            accepted = confirm(
                self,
                "Обнаружены высокие риски. Всё равно применить "
                "демонстрационную настройку?",
                "Расчёт выполнен в демонстрационном режиме, реальное оборудование "
                "не управляется.\n\n"
                + (f"Критичные предупреждения:\n{details}\n\n" if details else "")
                + "Применение настройки будет записано в журнал переналадок.",
            )
            if not accepted:
                self._log_event("Применение отменено оператором")
                self._journal.add_entry(
                    pipe, self._result, STATUS_CANCELLED, "Отмена применения"
                )
                self._set_status("Применение отменено оператором")
                return

        self._result = calculate_settings(pipe, self._machine, self._repository.raw)
        if self._result.manual_override:
            self._result = apply_manual_correction(
                pipe,
                self._machine,
                self._repository.raw,
                self._result.final_gap,
                self._result.manual_reason,
            )

        status = STATUS_MANUAL if self._result.manual_override else STATUS_APPLIED
        self._journal.add_entry(
            pipe, self._result, status, "Настройка применена наладчиком"
        )
        self._pipe = pipe
        self._is_applied = True
        self.machine_view.mark_applied()

        self._log_event(f"Настройка применена: уставка {format_mm(self._result.final_gap)}")
        self._log_event(f"Запись добавлена в журнал ({status})")
        self._set_status(
            f"Настройка применена: уставка {format_mm(self._result.final_gap)}, "
            f"{self._result.passes} прохода"
        )

        self.report_tab.set_result(pipe, self._result, True)
        self.journal_tab.refresh()
        self._log_event("Журнал и отчёт обновлены")

    def _on_manual(self) -> None:
        """Открывает диалог ручной коррекции уставки."""
        if self._result is None or not self._is_result_current:
            show_warning(
                self,
                "Ручная коррекция недоступна",
                "Сначала выполните расчёт настройки.",
            )
            return

        dialog = ManualCorrectionDialog(self, self._result, self._machine)
        if dialog.exec() != ManualCorrectionDialog.DialogCode.Accepted:
            pipe = self.input_panel.collect()
            self._journal.add_entry(
                pipe, self._result, STATUS_CANCELLED, "Ручная коррекция отменена"
            )
            self._log_event("Ручная коррекция отменена оператором")
            self._set_status("Ручная коррекция отменена")
            return

        gap, reason = dialog.values()
        pipe = self.input_panel.collect()
        result = apply_manual_correction(
            pipe, self._machine, self._repository.raw, gap, reason
        )
        self._result = result
        self._is_result_current = True
        self._is_applied = False

        self.result_panel.show_result(result, pipe.required_straightness)
        self.input_panel.set_apply_enabled(result.is_valid)
        self.input_panel.set_manual_enabled(result.is_valid)
        self.machine_view.mark_manual()
        self._journal.add_entry(
            pipe, result, STATUS_MANUAL, f"Уставка {format_mm(gap)}: {reason}"
        )
        self.journal_tab.refresh()
        self._log_event(
            f"Ручная коррекция: уставка {format_mm(result.final_gap)}, причина: {reason}"
        )
        self._log_event(f"Запись добавлена в журнал ({STATUS_MANUAL})")
        self._set_status(
            f"Ручная коррекция применена: {format_mm(result.final_gap)}"
        )

    def _on_reset(self) -> None:
        """Сбрасывает форму и схему в исходное состояние."""
        self.input_panel.reset()
        pipe = self.input_panel.collect()
        self._pipe = pipe
        self._result = None
        self._is_applied = False
        self.machine_view.set_pipe_diameter(pipe.diameter)
        self.machine_view.reset_to_machine_minimum()
        self.result_panel.clear()
        self._invalidate_result("Форма сброшена, готов к расчёту")
        self._log_event("Форма сброшена к исходным значениям")

    # ------------------------------------------------------------------
    # Демонстрационные сценарии
    # ------------------------------------------------------------------

    def _on_load_demo_order(self) -> None:
        """Открывает диалог выбора демо-заказа."""
        orders = self._repository.demo_orders
        if not orders:
            show_warning(
                self,
                "Демо-заказы недоступны",
                "В файле рецептов нет ни одного демо-заказа.",
            )
            return

        dialog = DemoOrderDialog(self, orders)
        if dialog.exec() != DemoOrderDialog.DialogCode.Accepted:
            return
        pipe = dialog.selected_order()
        if pipe is None:
            return
        self._load_pipe(pipe, f"Загружен демо-заказ {pipe.order_no}")

    def _load_pipe(self, pipe: Pipe, log_message: str) -> None:
        """Загружает трубу в форму и обновляет схему."""
        self.input_panel.fill_from_pipe(pipe)
        self._pipe = pipe
        self._is_result_current = False
        self._result = None
        self._is_applied = False
        self.result_panel.clear()
        self.input_panel.set_apply_enabled(False)
        self.input_panel.set_manual_enabled(False)
        self.machine_view.set_pipe_diameter(pipe.diameter)
        self.machine_view.reset_to_machine_minimum()
        self._set_status("Данные загружены, выполните расчёт")
        self._log_event(log_message)
        self._log_event(pipe_to_text(pipe))

    def _on_preset(self) -> None:
        """Применяет быстрый пресет."""
        dialog = PipePresetDialog(self)
        if dialog.exec() != PipePresetDialog.DialogCode.Accepted:
            return
        key = dialog.preset_key()
        title = dialog.preset_title()
        self.input_panel.apply_preset(key)
        self._log_event(f"Применён пресет: {title}")
        self._on_calculate()

    def _on_mistake_simulation(self) -> None:
        """Показывает последствия сохранения старой уставки."""
        pipe = self.input_panel.collect()
        issues = validate_pipe(pipe, self._machine)
        if issues:
            message = "; ".join(issue.message for issue in issues)
            show_warning(
                self,
                "Сначала укажите корректные параметры",
                f"Для симуляции нужен расчёт по корректной трубе.\n{message}",
            )
            return

        result = calculate_settings(pipe, self._machine, self._repository.raw)
        stale_gap = self._stale_gap_for(pipe)
        dialog = OperatorMistakeDialog(self, result, stale_gap, pipe)
        self._log_event(
            f"Симуляция ошибки наладчика: оставлена уставка "
            f"{format_mm(stale_gap)} вместо {format_mm(result.final_gap)}"
        )
        dialog.exec()

    def _stale_gap_for(self, pipe: Pipe) -> float:
        """Возвращает уставку предыдущего диаметра для симуляции ошибки."""
        base_recipes = self._repository.base_recipes
        previous = None
        for recipe in base_recipes:
            diameter = float(recipe["diameter"])
            if diameter < pipe.diameter:
                if previous is None or diameter > float(previous["diameter"]):
                    previous = recipe
        if previous is None:
            # Берём уставку для меньшего диаметра через эвристику.
            return round(pipe.diameter / 2.0 + 1.2 - pipe.wall_thickness * 0.1, 1)
        return round(
            float(previous["gap"])
            + (pipe.diameter - float(previous["diameter"])) * 0.5
            - (pipe.wall_thickness - float(previous["wall"])) * 0.15,
            1,
        )

    def _on_show_explanation(self) -> None:
        """Открывает диалог с обоснованием расчёта."""
        if self._result is None:
            show_warning(
                self,
                "Обоснование недоступно",
                "Сначала выполните расчёт настройки.",
            )
            return
        pipe = self.input_panel.collect()
        dialog = ExplanationDialog(self, pipe, self._result, self._machine)
        self._log_event("Открыто обоснование расчёта")
        dialog.exec()

    def _on_demo_scenario(self) -> None:
        """Проигрывает презентационный сценарий через таймеры."""
        if self._scenario_running:
            self._log_event("Демо-сценарий уже выполняется")
            return

        try:
            demo_pipe = self._repository.demo_order("ДЕМО-002")
        except Exception:  # noqa: BLE001 - демо должно быть устойчивым
            demo_pipe = None
        if demo_pipe is None:
            show_warning(
                self,
                "Демо-сценарий недоступен",
                "В файле рецептов нет заказа ДЕМО-002.",
            )
            return

        self._scenario_running = True
        self._is_applied = False
        self.tabs.setCurrentIndex(TAB_SETUP)
        self._log_event("Запущен демо-сценарий презентации")

        previous_diameter_pipe = demo_pipe.copy(
            diameter=48.0,
            operation="после механообработки",
            has_deflection=False,
            deflection=0.0,
        )

        self._schedule(700, self._scenario_step_load_previous, previous_diameter_pipe)
        self._schedule(1900, self._scenario_step_change_diameter)
        self._schedule(3000, self._scenario_step_enable_deflection)
        self._schedule(4100, self._scenario_step_calculate)
        self._schedule(5500, self._scenario_step_show_explanation)
        self._schedule(6900, self._scenario_step_apply)
        self._schedule(8300, self._scenario_step_show_report)

    def _schedule(self, delay_ms: int, callback: Any, *args: Any) -> None:
        """Планирует шаг сценария без блокировки интерфейса."""
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._run_scenario_step(callback, *args))
        self._scenario_timers.append(timer)
        timer.start(delay_ms)

    def _run_scenario_step(self, callback: Any, *args: Any) -> None:
        """Выполняет шаг сценария под защитой от исключений."""
        try:
            callback(*args)
        except Exception as exc:  # noqa: BLE001 - сценарий не должен ломать демо
            self._log_event(f"ОШИБКА сценария: {exc}")
            self._finish_scenario()

    def _scenario_step_load_previous(self, pipe: Pipe) -> None:
        """Шаг 1: показываем состояние до смены диаметра."""
        self._load_pipe(pipe, "Демо-сценарий: загружен заказ ДЕМО-002, диаметр 48 мм")
        stale = self._stale_gap_for(pipe)
        self._log_event(
            f"Текущая уставка на Ø48 мм: {format_mm(stale)}. "
            "Это значение подобрано вручную."
        )
        self._set_status("Демо-сценарий: труба Ø48 мм, старая уставка на ручном подборе")

    def _scenario_step_change_diameter(self) -> None:
        """Шаг 2: смена диаметра 48 → 57 мм."""
        self.input_panel.diameter_spin.setValue(57.0)
        self._pipe = self.input_panel.collect()
        self.machine_view.set_pipe_diameter(57.0)
        self._invalidate_result(STATUS_STALE)
        self.machine_view.mark_waiting()
        self._log_event(
            "Демо-сценарий: смена диаметра 48 → 57 мм. "
            "Старая уставка больше не подходит, требуется перерасчёт."
        )
        self._set_status("Демо-сценарий: смена диаметра 48 → 57 мм")

    def _scenario_step_enable_deflection(self) -> None:
        """Шаг 3: включение остаточного изгиба 6 мм/м."""
        self.input_panel.deflection_check.setChecked(True)
        self.input_panel.deflection_spin.setValue(6.0)
        self._pipe = self.input_panel.collect()
        self._invalidate_result(STATUS_STALE)
        self._log_event(
            "Демо-сценарий: труба поступила после гибки, остаточный изгиб 6 мм/м."
        )
        self._set_status("Демо-сценарий: обнаружен остаточный изгиб 6 мм/м")

    def _scenario_step_calculate(self) -> None:
        """Шаг 4: расчёт и предпросмотр перемещения валков."""
        self._log_event("Демо-сценарий: запуск расчёта")
        self._on_calculate()
        self._log_event("Демо-сценарий: смотрим на схему — валки идут к новой уставке")

    def _scenario_step_show_explanation(self) -> None:
        """Шаг 5: показ обоснования расчёта."""
        if self._result is None:
            return
        self._log_event("Демо-сценарий: обоснование расчёта")
        self._log_event(self._result.explanation.replace("\n", " | "))

    def _scenario_step_apply(self) -> None:
        """Шаг 6: применение настройки."""
        if self._result is None:
            return
        self._log_event("Демо-сценарий: применяем настройку")
        self._on_apply()

    def _scenario_step_show_report(self) -> None:
        """Шаг 7: переход на вкладку «Отчёт» и завершение сценария."""
        self.tabs.setCurrentIndex(TAB_REPORT)
        self.report_tab.refresh()
        self._log_event("Демо-сценарий завершён, открыта вкладка «Отчёт»")
        self._set_status("Демо-сценарий завершён: настройка применена и записана в журнал")
        self._finish_scenario()

    def _finish_scenario(self) -> None:
        """Снимает блокировку интерфейса после сценария."""
        for timer in self._scenario_timers:
            timer.stop()
        self._scenario_timers.clear()
        self._scenario_running = False

    # ------------------------------------------------------------------
    # Прочее
    # ------------------------------------------------------------------

    def _on_refresh_journal(self) -> None:
        """Обновляет журнал и отчёт."""
        self.journal_tab.refresh()
        self.report_tab.refresh()
        self._log_event("Журнал и отчёт обновлены")

    def _go_to_about(self) -> None:
        """Переходит на вкладку «О системе»."""
        self.tabs.setCurrentIndex(TAB_ABOUT)

    def _on_logout(self) -> None:
        """Просит сменить пользователя и сообщает об этом наружу.

        Окно входа открывает `main.py`, а не сам слот: только там решается,
        что делать при отмене входа — закрыть программу или остаться.
        """
        # Идущий демо-сценарий останавливаем: его таймеры управляют
        # уже несуществующей после смены пользователя формой.
        self._finish_scenario()

        if not confirm(
            self,
            "Сменить пользователя?",
            f"Вы выйдете из учётной записи «{self._session.operator_name}».\n\n"
            "Записи в журнале переналадок сохранятся: они уже записаны "
            "на диск. Несохранённый расчёт и выбранный заказ будут сброшены.",
            accept_text="Выйти",
        ):
            return

        self._log_event(
            f"Выход из учётной записи: {self._session.operator_name} "
            f"({self._session.role_title})"
        )
        self.logoutRequested.emit()

    def _on_tab_changed(self, index: int) -> None:
        """Обновляет содержимое вкладки при переключении."""
        if index == TAB_JOURNAL:
            self.journal_tab.refresh()
        elif index == TAB_REPORT:
            if self._result is not None and self._pipe is not None:
                self.report_tab.set_result(self._pipe, self._result, self._is_applied)
            else:
                self.report_tab.refresh()

    def closeEvent(self, event: Any) -> None:  # type: ignore[override]
        """Останавливает таймеры сценария при закрытии окна."""
        self._finish_scenario()
        super().closeEvent(event)