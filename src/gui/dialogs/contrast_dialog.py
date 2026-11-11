"""Dedicated standalone contrast controls."""

from PySide6.QtWidgets import QWidget

from gui.dialogs.base_operation_dialog import BaseOperationDialog


class ContrastDialog(BaseOperationDialog):
    """Configure contrast without other enhancement stages."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise contrast settings and shared controls.

        :param parent: Optional owning widget.
        """
        super().__init__("contrast", parent)

    def build_parameters(self) -> None:
        """Add contrast and encoding parameters."""
        self.add_field("contrast", "Contrast")
        self.add_field("crf", "CRF")
        self.add_field("preset", "Encoding preset")
        self.controls["contrast"].setToolTip(
            "0–3; 1 is neutral. Below 1 reduces contrast; above 1 increases it. "
            "Higher values may clip highlights and obscure shadow detail."
        )
