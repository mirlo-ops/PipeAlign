"""Окно входа в программу.

Задача окна — отличить оператора станка от контролёра ОТК и передать
главному окну сессию, по которой строятся права. Само окно намеренно
простое: логин и пароль, роль определяется учётной записью. Никаких
«запомнить меня», смены пароля и регистрации — проект демонстрационный,
а лишние элементы входа только мешают на защите разобраться.

Пароли в окне не показываются: подсказка рядом с полем ввода выглядит
несерьёзно и приучает показывать пароль настоящим пользователям.
Демонстрационные учётные записи описаны в README.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app import APP_DISPLAY_NAME, APP_VERSION, DISCLAIMER
from app.models.machine import MachineConfig
from app.services.auth_service import (
    ERROR_INVALID_CREDENTIALS,
    Session,
    authenticate,
    role_summary,
)

#: Ширина окна входа: достаточно для карточки, экран не перекрывает.
LOGIN_WIDTH = 470


class LoginDialog(QDialog):
    """Модальное окно входа; роль берётся из учётной записи.

    Роль не выбирается вручную. Это исключает ситуацию, когда оператор
    случайно получает права контролёра, и убирает лишний элемент из формы.
    """

    def __init__(self, machine: MachineConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._session: Session | None = None
        self._machine = machine

        self.setWindowTitle(f"{APP_DISPLAY_NAME} — вход")
        self.setModal(True)
        self.setFixedWidth(LOGIN_WIDTH)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_header())
        layout.addWidget(self._build_body(), 1)
        layout.addWidget(self._build_footer())

        self._login_edit.setFocus()

    # ------------------------------------------------------------------
    # Построение окна
    # ------------------------------------------------------------------

    def _build_header(self) -> QWidget:
        """Шапка: название программы, машина и версия."""
        container = QWidget()
        container.setObjectName("LoginHeader")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(26, 24, 26, 18)
        layout.setSpacing(5)

        title = QLabel(APP_DISPLAY_NAME)
        title_font = QFont("Segoe UI")
        title_font.setPointSize(17)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setObjectName("LoginTitle")
        layout.addWidget(title)

        subtitle = QLabel(
            f"Ассистент переналадки · {self._machine.name} · версия {APP_VERSION}"
        )
        subtitle.setObjectName("SubTitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        return container

    def _build_body(self) -> QWidget:
        """Поля логина и пароля, ошибка входа и напоминание о ролях."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(26, 2, 26, 2)
        layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(9)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self._login_edit = QLineEdit()
        self._login_edit.setPlaceholderText("Логин")
        self._login_edit.setMaxLength(64)
        self._login_edit.textChanged.connect(self._clear_error)
        form.addRow(self._field_label("Логин"), self._login_edit)

        self._password_edit = QLineEdit()
        self._password_edit.setPlaceholderText("Пароль")
        self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_edit.setMaxLength(64)
        self._password_edit.textChanged.connect(self._clear_error)
        # Enter в поле пароля отправляет форму: привычное поведение на кассе.
        self._password_edit.returnPressed.connect(self._on_submit)
        form.addRow(self._field_label("Пароль"), self._password_edit)

        layout.addLayout(form)

        self._error_label = QLabel()
        self._error_label.setObjectName("LoginError")
        self._error_label.setWordWrap(True)
        self._error_label.setVisible(False)
        layout.addWidget(self._error_label)

        layout.addWidget(self._build_roles_hint())
        layout.addStretch(1)
        return container

    def _build_roles_hint(self) -> QWidget:
        """Напоминание, какие роли доступны в программе."""
        box = QFrame()
        box.setObjectName("LoginHintBox")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.setSpacing(5)

        caption = QLabel("В программе доступны две роли:")
        caption.setObjectName("LoginHintTitle")
        layout.addWidget(caption)

        for text in role_summary():
            line = QLabel(text)
            line.setObjectName("LoginHintText")
            line.setWordWrap(True)
            layout.addWidget(line)

        return box

    def _build_footer(self) -> QWidget:
        """Кнопки входа и выхода."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(26, 14, 26, 18)
        layout.setSpacing(12)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch(1)

        cancel_button = QPushButton("Отмена")
        cancel_button.setMinimumHeight(38)
        cancel_button.clicked.connect(self.reject)
        buttons.addWidget(cancel_button)

        login_button = QPushButton("Войти")
        login_button.setObjectName("PrimaryButton")
        login_button.setDefault(True)
        login_button.setMinimumHeight(38)
        login_button.clicked.connect(self._on_submit)
        buttons.addWidget(login_button)

        layout.addLayout(buttons)

        note = QLabel(DISCLAIMER)
        note.setObjectName("LoginNote")
        note.setWordWrap(True)
        layout.addWidget(note)
        return container

    @staticmethod
    def _field_label(text: str) -> QLabel:
        """Подпись поля формы."""
        label = QLabel(text)
        label.setObjectName("FieldLabel")
        return label

    # ------------------------------------------------------------------
    # Поведение
    # ------------------------------------------------------------------

    def _on_submit(self) -> None:
        """Проверяет учётные данные и закрывает окно при успехе."""
        session = authenticate(self._login_edit.text(), self._password_edit.text())
        if session is None:
            # Пароль очищаем до показа ошибки и блокируем сигналы: иначе
            # textChanged от очистки тут же спрятал бы сообщение.
            self._password_edit.blockSignals(True)
            self._password_edit.clear()
            self._password_edit.blockSignals(False)
            self._show_error(ERROR_INVALID_CREDENTIALS)
            self._password_edit.setFocus()
            return

        self._session = session
        self.accept()

    def _show_error(self, message: str) -> None:
        """Показывает текст ошибки под полями ввода."""
        self._error_label.setText(message)
        self._error_label.setVisible(True)

    def _clear_error(self) -> None:
        """Убирает ошибку, как только пользователь начал исправлять ввод."""
        self._error_label.setVisible(False)

    def session(self) -> Session | None:
        """Возвращает сессию успешного входа."""
        return self._session
