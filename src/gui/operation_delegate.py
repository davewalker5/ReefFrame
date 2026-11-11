"""Theme-aware rendering for the operation menu separator."""

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtGui import QPainter, QPalette
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem


class OperationDelegate(QStyledItemDelegate):
    """Keep native option styling while drawing a clearly visible separator."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        """Draw separators using the enabled text colour instead of a faint native rule.

        :param painter: Painter supplied by the popup view.
        :param option: Item rectangle and current theme palette.
        :param index: Model entry identifying an option or separator.
        """
        if index.data(Qt.ItemDataRole.AccessibleDescriptionRole) != "separator":
            super().paint(painter, option, index)
            return
        painter.save()
        # Separators are disabled items; use the active palette deliberately so
        # dark themes do not render this structural line as disabled text.
        painter.setPen(option.palette.color(QPalette.ColorGroup.Active, QPalette.ColorRole.Text))
        rectangle = option.rect.adjusted(6, 0, -6, 0)
        painter.drawLine(
            rectangle.left(), rectangle.center().y(), rectangle.right(), rectangle.center().y()
        )
        painter.restore()
