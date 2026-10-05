"""Вкладка «О системе»: защита проекта, формулы и план внедрения."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QScrollArea,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app import APP_VERSION
from app.models.machine import MachineConfig
from app.services.auth_service import accounts_without_passwords, role_summary
from app.services.journal_service import JournalService
from app.ui.dialogs import StylePreviewWidget
from app.utils.paths import log_directory

#: План внедрения проекта — используется и в презентации, и в отчёте.
IMPLEMENTATION_PLAN: tuple[str, ...] = (
    "Советчик: программа считает уставку и объясняет решение, оператор применяет "
    "настройку вручную. Текущая версия проекта.",
    "Интеграция с заказ-нарядом: рецепты загружаются из системы производственного "
    "планирования, а не из локального файла.",
    "Датчики положения валков: контроль фактической установки уставки и "
    "подтверждение перемещения валков.",
    "Полуавтоматическая переналадка: программа выдаёт команду на перемещение "
    "по подтверждению оператора.",
    "Адаптивная правка: уставка корректируется по фактически измеренной "
    "кривизне после прохода.",
)


class AboutTab(QScrollArea):
    """Текстовая страница для защиты проекта.

    Здесь собрано всё, что обычно спрашивают на защите: проблема,
    решение, формула, ограничения и дорожная карта внедрения.
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

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        layout.addWidget(self._build_title_block())
        layout.addWidget(self._build_browser(), 1)
        layout.addWidget(self._build_style_preview())
        layout.addWidget(self._build_footer())

        self.setWidget(container)

    def _build_title_block(self) -> QWidget:
        """Шапка с названием проекта и версией."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        title = QLabel("ТрубоНастрой / PipeAlign")
        title_font = QFont("Segoe UI")
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: #ff8c00;")
        layout.addWidget(title)

        subtitle = QLabel(
            f"Демонстрационный ассистент переналадки косовалковой правильной "
            f"машины · версия {APP_VERSION} · {self._machine.name}"
        )
        subtitle.setObjectName("SubTitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        disclaimer = QLabel(
            "Демонстрационный прототип. Расчёты модельные. "
            "Реальное управление оборудованием требует отдельной валидации."
        )
        disclaimer.setObjectName("Disclaimer")
        disclaimer.setWordWrap(True)
        disclaimer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(disclaimer)

        return container

    def _build_browser(self) -> QTextBrowser:
        """Основной текст страницы."""
        browser = QTextBrowser()
        browser.setOpenExternalLinks(False)
        browser.setMinimumHeight(520)
        browser.setHtml(self._build_html())
        return browser

    def _build_html(self) -> str:
        """Собирает HTML-страницу «О системе»."""
        plan_items = "\n".join(
            f"<li>{item}</li>" for item in IMPLEMENTATION_PLAN
        )
        machine = self._machine
        role_rows = "".join(
            f"<tr><td style='padding:2px 14px 2px 0;'>{account.full_name}</td>"
            f"<td style='padding:2px 14px 2px 0; color:#a0aab5;'>{account.position}</td>"
            f"<td style='color:#a0aab5;'>{account.login}</td></tr>"
            for account in accounts_without_passwords()
        )
        accounts_html = (
            "<table style='margin:6px 0 12px 0;'>"
            "<tr style='color:#a0aab5;'>"
            "<th align='left' style='padding:0 14px 4px 0;'>Сотрудник</th>"
            "<th align='left' style='padding:0 14px 4px 0;'>Должность</th>"
            "<th align='left' style='padding:0 14px 4px 0;'>Логин</th>"
            "</tr>"
            f"{role_rows}</table>"
        )
        roles_html = "".join(f"<li>{text}</li>" for text in role_summary())
        formula = (
            "Итоговая уставка = Базовая уставка<br/>"
            "<span style='color:#a0aab5'>"
            "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
            "&nbsp;+ Поправка на материал<br/>"
            "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
            "&nbsp;+ Поправка на изгиб<br/>"
            "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
            "&nbsp;+ Поправка на операцию"
            "</span>"
        )
        journal_dir = log_directory()

        return f"""
        <html>
        <head><meta charset="utf-8"/></head>
        <body style="color:#e6e6e6; font-family:'Segoe UI',sans-serif; font-size:10pt;">
          <h2 style="color:#ff8c00;">Проблема</h2>
          <p>
            После гибки, сварки, механо- и термообработки труба поступает на
            косовалковую правильную машину с остаточным изгибом. Наладчик
            подбирает зазор между валками вручную: по памяти, «на глаз» и по
            нескольким пробным прогонам. Это даёт 30–40 минут переналадки,
            4 пробных прогона и брак по кривизне в среднем около 6 % партии.
          </p>

          <h2 style="color:#ff8c00;">Решение</h2>
          <p>
            ТрубоНастрой рассчитывает уставку между валками по параметрам трубы:
            диаметру, толщине стенки, марке стали, технологической операции и
            остаточному изгибу. Программа выдаёт уставку, число проходов и
            скорость подачи, а также <b>объясняет решение человеческим языком</b>
            и показывает, чего стоит ошибка переналадки.
          </p>

          <h2 style="color:#ff8c00;">Принцип работы</h2>
          <ol>
            <li>Оператор вводит параметры трубы или загружает заказ из справочника.</li>
            <li>Расчётный модуль выбирает базовую уставку из справочника рецептов.</li>
            <li>Добавляются поправки на материал, остаточный изгиб и операцию.</li>
            <li>Итог ограничивается рабочим диапазоном машины
                ({machine.min_gap:g}–{machine.max_gap:g} мм).</li>
            <li>Определяются число проходов, скорость подачи и прогноз кривизны.</li>
            <li>Оценивается уровень риска и ожидаемый эффект по времени и браку.</li>
            <li>Применённая настройка фиксируется в журнале переналадок.</li>
          </ol>

          <h2 style="color:#ff8c00;">Формула расчёта</h2>
          <p style="font-family:Consolas,monospace; font-size:11pt; color:#ff8c00;">
            {formula}
          </p>
          <p>
            <b>Базовая уставка</b> — точное совпадение (диаметр, стенка) в
            справочнике рецептов; при отсутствии точного совпадения берётся
            ближайший рецепт с коррекцией по диаметру и стенке; если справочник
            пуст, применяется эвристическая формула D/2 + 1,2 − S × 0,1.<br/>
            <b>Поправка на материал</b> — зависит от марки стали: упрочняемые
            марки требуют большего зазора и меньшей скорости.<br/>
            <b>Поправка на изгиб</b> — линейная интерполяция по кривой
            «изгиб → компенсация»: 0 мм/м → 0,0 мм, 6 мм/м → 0,6 мм,
            12 мм/м → 1,5 мм, 30 мм/м → 4,0 мм.<br/>
            <b>Поправка на операцию</b> — в версии 0.1 равна нулю и зарезервирована
            для следующих версий модели.
          </p>

          <h2 style="color:#ff8c00;">Роли и доступ</h2>
          <p>
            Программа открывается с окном входа. Роль определяется учётной
            записью и не выбирается вручную, поэтому оператор не может
            случайно получить права контролёра. Расчёт от роли не зависит —
            обе роли получают одну и ту же уставку.
          </p>
          <p>
            <b>Демонстрационные учётные записи</b> (пароли — в README проекта):
          </p>
          {accounts_html}
          <p>Что доступно каждой роли:</p>
          <ul>{roles_html}</ul>

          <h2 style="color:#ff8c00;">Ограничения</h2>
          <ul>
            <li>Авторизация — учебная заглушка: пароли хранятся в исходном
                коде открытым текстом и сравниваются напрямую. Настоящей
                системы контроля доступа здесь нет.</li>
            <li>Это не система управления станком: программа не выдаёт команд
                оборудованию и не контролирует его положение.</li>
            <li>Все коэффициенты демонстрационные и не являются
                инженерно достоверными.</li>
            <li>Не моделируются биение валков, точность позиционирования,
                тепловые расширения и обратная связь по фактической кривизне.</li>
            <li>Расчётная модель не сертифицирована и требует натурной валидации
                перед применением в серийном производстве.</li>
          </ul>

          <h2 style="color:#ff8c00;">План внедрения</h2>
          <ol>{plan_items}</ol>

          <h2 style="color:#ff8c00;">Технологии</h2>
          <p>
            Python 3.10+, PySide6 (QtWidgets), PyInstaller, JSON, стандартная
            библиотека. Приложение работает локально: без сервера, без базы
            данных, без сетевых запросов и без реального оборудования.
          </p>

          <h2 style="color:#ff8c00;">Данные приложения</h2>
          <p>
            Журнал переналадок: <span style="font-family:Consolas,monospace;">
            {journal_dir / 'journal.json'}</span><br/>
            Резервные копии журнала создаются рядом в этом каталоге.
          </p>
        </body>
        </html>
        """

    def _build_style_preview(self) -> QWidget:
        """Живой пример элементов управления тёмной темы."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        caption = QLabel("Элементы управления темы:")
        caption.setObjectName("FieldLabel")
        layout.addWidget(caption)
        layout.addWidget(StylePreviewWidget())
        return container

    def _build_footer(self) -> QWidget:
        """Подвал с копирайтом и напоминанием о демо-режиме."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        footer = QLabel(
            "Учебный демонстрационный проект. Вымышленное производство: "
            "ООО «СтальТрубПром». Демо-режим: реальное оборудование не управляется."
        )
        footer.setObjectName("HintLabel")
        footer.setWordWrap(True)
        layout.addWidget(footer)
        return container