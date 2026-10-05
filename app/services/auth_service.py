"""Демонстрационная авторизация: учётные записи и права ролей.

Модуль намеренно простой и Qt-free, чтобы проверяться обычными тестами
без графической подсистемы — так же, как репозиторий и журнал.

ВНИМАНИЕ: это учебная заглушка, а не система контроля доступа. Пароли
лежат в исходном коде открытым текстом и сравниваются напрямую. В реальной
системе вместо этого нужен хеш пароля (например, PBKDF2 с солью на
пользователя), хранение учётных записей вне репозитория и журнал входов.
Показывать этот пароль на экране входа нельзя — вместо него в диалоге
перечислены роли, а демонстрационные пароли описаны в README.

Роли отражают реальный участок:

* оператор станка работает у машины и каждый запуск вводит только геометрию
  трубы; номер заказа и экономика переналадки ему не нужны;
* контролёр ОТК проверяет выполненную настройку и оформляет документы, поэтому
  видит заказ, партию и ожидаемый эффект.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Ключ роли оператора станка.
ROLE_OPERATOR = "operator"

#: Ключ роли контролёра ОТК.
ROLE_CONTROLLER = "controller"

#: Подписи ролей для интерфейса.
ROLE_TITLES: dict[str, str] = {
    ROLE_OPERATOR: "Оператор станка",
    ROLE_CONTROLLER: "Контролёр ОТК",
}


@dataclass(frozen=True)
class RoleProfile:
    """Что позволяет делать роль в интерфейсе.

    Права описаны данными, а не условиями в коде виджетов: так список
    ролей читается как документация, а добавление новой роли не требует
    правок в панелях.
    """

    #: Ключ роли, используется в проверках и журнале сессии.
    key: str

    #: Человекочитаемое название роли.
    title: str

    #: Короткое пояснение для окна входа.
    description: str

    #: Показывать группу «Заказ и операция» (номер заказа, партия, оператор).
    show_order_form: bool

    #: Показывать группу «Ожидаемый эффект» (экономия времени, брак).
    show_effect_panel: bool


#: Профили ролей. Оператор сознательно получает урезанный набор панелей.
ROLE_PROFILES: dict[str, RoleProfile] = {
    ROLE_OPERATOR: RoleProfile(
        key=ROLE_OPERATOR,
        title=ROLE_TITLES[ROLE_OPERATOR],
        description="Геометрия трубы, уставка, проходы и скорость подачи",
        show_order_form=False,
        show_effect_panel=False,
    ),
    ROLE_CONTROLLER: RoleProfile(
        key=ROLE_CONTROLLER,
        title=ROLE_TITLES[ROLE_CONTROLLER],
        description=(
            "Полный доступ: заказ, партия, расчёт, ожидаемый эффект, журнал"
        ),
        show_order_form=True,
        show_effect_panel=True,
    ),
}


@dataclass(frozen=True)
class UserAccount:
    """Учётная запись пользователя.

    Пароль не хранится в объекте: он нужен только в момент проверки входа,
    поэтому остаётся в таблице :data:`ACCOUNTS`.
    """

    #: Логин без пробелов, вводится в поле «Логин».
    login: str

    #: Фамилия и инициалы, попадают в поле оператора и в журнал.
    full_name: str

    #: Должность, показывается в строке состояния.
    position: str

    #: Ключ роли из :data:`ROLE_PROFILES`.
    role: str

    @property
    def role_profile(self) -> RoleProfile:
        """Профиль прав для роли этой учётной записи.

        Неизвестная роль даёт профиль оператора: это безопасное поведение,
        потому что лишние панели лучше скрыть, чем показать.
        """
        return ROLE_PROFILES.get(self.role, ROLE_PROFILES[ROLE_OPERATOR])


@dataclass(frozen=True)
class AccountRecord:
    """Строка демонстрационной таблицы учётных записей."""

    account: UserAccount
    password: str


@dataclass(frozen=True)
class Session:
    """Результат успешного входа.

    Хранится только в памяти и только на время работы приложения: файл
    сессии не создаётся, чтобы программа не оставляла следов входа на диске.
    """

    account: UserAccount
    login_time: str

    @property
    def role_profile(self) -> RoleProfile:
        """Профиль прав этой роли."""
        return self.account.role_profile

    @property
    def role_title(self) -> str:
        """Название роли для интерфейса."""
        return self.account.role_profile.title

    @property
    def show_order_form(self) -> bool:
        """Показывать ли группу «Заказ и операция»."""
        return self.account.role_profile.show_order_form

    @property
    def show_effect_panel(self) -> bool:
        """Показывать ли группу «Ожидаемый эффект»."""
        return self.account.role_profile.show_effect_panel

    @property
    def operator_name(self) -> str:
        """ФИО для поля оператора и записей журнала."""
        return self.account.full_name


#: Демонстрационные учётные записи. Пароли — учебные, не используются нигде.
ACCOUNTS: tuple[AccountRecord, ...] = (
    AccountRecord(
        account=UserAccount(
            login="akulov",
            full_name="Акулов Л.И.",
            position="Оператор правильной машины",
            role=ROLE_OPERATOR,
        ),
        password="1234",
    ),
    AccountRecord(
        account=UserAccount(
            login="korablev",
            full_name="Кораблев М.Д.",
            position="Контролёр ОТК",
            role=ROLE_CONTROLLER,
        ),
        password="4321",
    ),
)

#: Сообщение при неверном логине или пароле.
#: Единое для обоих случаев: подсказка «логин верный, пароль нет» помогала бы
#: перебирать учётные записи в демонстрации.
ERROR_INVALID_CREDENTIALS = "Неверный логин или пароль"


def accounts_without_passwords() -> tuple[UserAccount, ...]:
    """Возвращает список учётных записей без паролей.

    Нужен для подсказок и тестов: пароль не должен покидать модуль.
    """
    return tuple(record.account for record in ACCOUNTS)


def login_keys(full_name: str) -> tuple[str, ...]:
    """Возвращает варианты записи ФИО, которые считаются одним логином.

    Сотрудник вводит ФИО так, как оно указано в наряде, а не так, как
    записано в служебной таблице: «Акулов Л.И.», «Акулов» или «акулов
    л.и.» — это один и тот же человек. Ключи сравниваются без учёта
    регистра, пробелов и точек, чтобы лишние символы при ручном вводе
    не мешали войти.
    """
    surname = full_name.split()[0] if full_name.split() else full_name
    return (
        _normalize(full_name),
        _normalize(surname),
    )


def _normalize(value: str) -> str:
    """Ключ сравнения логина: без регистра, пробелов и точек."""
    return "".join(value.split()).casefold().replace(".", "")


def authenticate(login: str, password: str) -> Session | None:
    """Проверяет логин и пароль, возвращает сессию или ``None``.

    Логин нечувствителен к регистру, пробелам по краям и точкам в
    инициалах: человек вводит « Акулов Л.И. » так же, как «akulov».
    Пароль, наоборот, сравнивается точно — лишний пробел в пароле
    должен давать ошибку, а не молчаливый вход.
    """
    normalized = _normalize(login)
    for record in ACCOUNTS:
        account = record.account
        accepted = {_normalize(account.login)} | set(login_keys(account.full_name))
        if normalized not in accepted:
            continue
        if record.password == password:
            from app.utils.formatting import now_iso

            return Session(account=account, login_time=now_iso())
        # Пароль неверный: дальше не ищем, чтобы по времени ответа
        # нельзя было перебирать учётные записи подряд.
        return None
    return None


def role_summary() -> tuple[str, ...]:
    """Строки «роль — что доступно» для окна входа и вкладки «О системе»."""
    return tuple(
        f"{profile.title} — {profile.description}"
        for profile in ROLE_PROFILES.values()
    )
