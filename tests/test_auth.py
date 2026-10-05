"""Тесты демонстрационной авторизации.

Модуль ``app.services.auth_service`` не зависит от Qt, поэтому проверяется
обычными вызовами без графической подсистемы.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.auth_service import (  # noqa: E402
    ACCOUNTS,
    ERROR_INVALID_CREDENTIALS,
    ROLE_CONTROLLER,
    ROLE_OPERATOR,
    ROLE_PROFILES,
    accounts_without_passwords,
    authenticate,
    role_summary,
)


class TestAuthenticate:
    """Проверка логина и пароля."""

    def test_operator_login_succeeds(self) -> None:
        """Оператор входит по своей учётной записи."""
        session = authenticate("akulov", "1234")
        assert session is not None
        assert session.operator_name == "Акулов Л.И."
        assert session.account.role == ROLE_OPERATOR

    def test_controller_login_succeeds(self) -> None:
        """Контролёр ОТК входит по своей учётной записи."""
        session = authenticate("korablev", "4321")
        assert session is not None
        assert session.operator_name == "Кораблев М.Д."
        assert session.account.role == ROLE_CONTROLLER

    @pytest.mark.parametrize(
        ("login", "password"),
        [
            ("akulov", "4321"),   # пароль другой роли
            ("korablev", "1234"),  # пароль другой роли
            ("akulov", "12345"),  # лишний символ
            ("akulov", ""),       # пустой пароль
            ("", "1234"),         # пустой логин
            ("unknown", "1234"),  # нет такой учётной записи
        ],
    )
    def test_wrong_credentials_rejected(self, login: str, password: str) -> None:
        """Неверные данные не дают сессию."""
        assert authenticate(login, password) is None

    def test_login_is_case_insensitive(self) -> None:
        """Регистр логина не важен: человек вводит как удобнее."""
        assert authenticate("AKULOV", "1234") is not None
        assert authenticate("  Akulov  ", "1234") is not None

    @pytest.mark.parametrize(
        "written_name",
        [
            "Акулов Л.И.",   # так ФИО указано в наряде
            "Акулов Л. И.",  # с пробелом перед точкой
            "Акулов",        # только фамилия
            "акулов ли",     # без точек и в нижнем регистре
            "  Акулов Л.И.  ",
        ],
    )
    def test_full_name_is_accepted_as_login(self, written_name: str) -> None:
        """Сотрудник вводит ФИО так, как оно записано в наряде.

        Логин в служебной таблице — латиницей, но человек вводит ФИО
        кириллицей. Отказ здесь означал бы, что сотрудник не может войти.
        """
        session = authenticate(written_name, "1234")
        assert session is not None
        assert session.operator_name == "Акулов Л.И."

    def test_full_name_accepted_for_controller(self) -> None:
        """То же правило работает для второй роли."""
        session = authenticate("Кораблев М.Д.", "4321")
        assert session is not None
        assert session.operator_name == "Кораблев М.Д."

    def test_surname_of_another_person_is_rejected(self) -> None:
        """Фамилия, похожая на существующую, не подходит."""
        assert authenticate("Акулова", "1234") is None
        assert authenticate("Кораблев", "1234") is None

    def test_password_is_case_sensitive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Логин нечувствителен к регистру, а пароль — чувствителен.

        Пароли демонстрации состоят из цифр, поэтому регистр логина не
        позволяет проверить чувствительность пароля. Подменяем таблицу
        записей на набор с буквенным паролем.
        """
        import app.services.auth_service as module

        monkeypatch.setattr(
            module,
            "ACCOUNTS",
            (
                module.AccountRecord(
                    account=module.UserAccount(
                        login="tester",
                        full_name="Тест Тестов",
                        position="—",
                        role=ROLE_OPERATOR,
                    ),
                    password="Secret",
                ),
            ),
        )

        assert authenticate("tester", "Secret") is not None
        assert authenticate("TESTER", "Secret") is not None
        assert authenticate("tester", "secret") is None
        assert authenticate("tester", "SECRET") is None

    def test_password_is_not_trimmed(self) -> None:
        """Пробел в пароле считается ошибкой, а не лишним символом."""
        assert authenticate("akulov", " 1234 ") is None

    def test_error_message_is_shared(self) -> None:
        """Сообщение одно для неверного логина и неверного пароля."""
        assert authenticate("akulov", "0000") is None
        assert authenticate("nobody", "0000") is None
        assert "Неверный" in ERROR_INVALID_CREDENTIALS


class TestRolePermissions:
    """Права ролей определяют видимость панелей."""

    def test_operator_has_no_order_form(self) -> None:
        """Оператор не вводит номер заказа у станка."""
        session = authenticate("akulov", "1234")
        assert session is not None
        assert session.show_order_form is False
        assert session.show_effect_panel is False

    def test_controller_sees_everything(self) -> None:
        """Контролёр ОТК видит заказ и ожидаемый эффект."""
        session = authenticate("korablev", "4321")
        assert session is not None
        assert session.show_order_form is True
        assert session.show_effect_panel is True

    def test_every_account_has_known_role(self) -> None:
        """Учётная запись не может ссылаться на несуществующую роль."""
        for account in accounts_without_passwords():
            assert account.role in ROLE_PROFILES

    def test_operator_profile_has_no_extra_panels(self) -> None:
        """Оператор не получает больше прав, чем контролёр."""
        operator = ROLE_PROFILES[ROLE_OPERATOR]
        controller = ROLE_PROFILES[ROLE_CONTROLLER]
        assert operator.show_order_form <= controller.show_order_form
        assert operator.show_effect_panel <= controller.show_effect_panel

    def test_unknown_role_falls_back_to_operator(self) -> None:
        """Неизвестная роль даёт минимальные права, а не максимальные."""
        from app.services.auth_service import UserAccount

        stranger = UserAccount(
            login="stranger",
            full_name="Кто-то",
            position="—",
            role="unknown_role",
        )
        assert stranger.role_profile is ROLE_PROFILES[ROLE_OPERATOR]


class TestSession:
    """Данные сессии."""

    def test_login_time_recorded(self) -> None:
        """Время входа фиксируется в формате ISO."""
        session = authenticate("akulov", "1234")
        assert session is not None
        assert len(session.login_time) == 19
        assert session.login_time[4] == "-"

    def test_role_title_available_for_status_bar(self) -> None:
        """Название роли доступно для строки состояния."""
        session = authenticate("korablev", "4321")
        assert session is not None
        assert session.role_title == "Контролёр ОТК"


class TestDemoData:
    """Демонстрационные данные удобны для показа."""

    def test_accounts_cover_both_roles(self) -> None:
        """В программе есть и оператор, и контролёр."""
        roles = {account.role for account in accounts_without_passwords()}
        assert roles == {ROLE_OPERATOR, ROLE_CONTROLLER}

    def test_logins_are_unique(self) -> None:
        """Логины не повторяются."""
        logins = [record.account.login for record in ACCOUNTS]
        assert len(logins) == len(set(logins))

    def test_passwords_not_exposed_by_public_api(self) -> None:
        """Список для интерфейса не содержит паролей."""
        for account in accounts_without_passwords():
            assert not hasattr(account, "password")

    def test_role_summary_mentions_both_roles(self) -> None:
        """Сводка ролей пригодна для окна входа."""
        summary = role_summary()
        assert len(summary) == len(ROLE_PROFILES)
        assert any("Оператор" in line for line in summary)
        assert any("Контролёр" in line for line in summary)
