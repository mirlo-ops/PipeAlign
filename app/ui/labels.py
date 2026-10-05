"""Переиспользуемые виджеты интерфейса."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel


class ElidedLabel(QLabel):
    """Метка, которая сокращает текст многоточием, а не обрезает.

    Нужна там, где виджет вынужден сжиматься: в строке состояния при
    минимальной ширине окна не помещаются ни имя машины, ни длинный
    текст статуса. Обычный :class:`QLabel` в этом случае срезает строку
    на полуслове, и сотрудник не понимает, что там написано.

    Текст сокращается в :meth:`resizeEvent` и передаётся обычному
    :meth:`setText`, поэтому отрисовку, шрифт и цвета темы по-прежнему
    делает Qt. Полный текст хранится отдельно и доступен через
    :meth:`full_text` и подсказку.
    """

    def __init__(self, text: str = "", parent: object | None = None) -> None:
        super().__init__(parent)  # type: ignore[arg-type]
        self._full_text = text
        self._show_full_text_tooltip = True
        self.setMinimumWidth(0)
        # Текст из конструктора тоже должен попасть в подсказку и
        # быть обработан сокращением, поэтому инициализация идёт
        # через собственный setText.
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802 - имя из Qt
        """Запоминает полный текст и показывает его с сокращением."""
        self._full_text = text
        if self._show_full_text_tooltip:
            self.setToolTip(text)
        self._apply_elide()

    def full_text(self) -> str:
        """Возвращает текст без сокращения."""
        return self._full_text

    def set_elide_tooltip(self, enabled: bool) -> None:
        """Включает или отключает подсказку с полным текстом.

        Нужно меткам, у которых подсказка уже занята о чём-то своём.
        """
        self._show_full_text_tooltip = enabled
        if not enabled:
            self.setToolTip("")

    def resizeEvent(self, event: object) -> None:  # noqa: N802 - имя из Qt
        """Пересчитывает сокращение при изменении ширины."""
        super().resizeEvent(event)  # type: ignore[arg-type]
        self._apply_elide()

    def _apply_elide(self) -> None:
        """Ставит в метку сокращённый текст вместо полного."""
        metrics = self.fontMetrics()
        elided = metrics.elidedText(
            self._full_text,
            Qt.TextElideMode.ElideRight,
            max(0, self.width()),
        )
        if elided != self.text():
            # Вызываем QLabel.setText напрямую, иначе вызовем свой
            # setText и потеряем полный текст в рекурсии.
            super().setText(elided)