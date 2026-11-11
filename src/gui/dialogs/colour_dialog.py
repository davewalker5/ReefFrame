"""Dedicated colour correction controls."""

from PySide6.QtWidgets import QWidget

from gui.dialogs.base_operation_dialog import BaseOperationDialog


class ColourDialog(BaseOperationDialog):
    """Configure independent colour correction."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise correction controls.

        :param parent: Optional owning widget.
        """
        super().__init__("colour", parent)

    def build_parameters(self) -> None:
        """Add correction and encoding controls."""
        self.add_field("red_gain", "Red gain")
        self.add_field("green_gain", "Green gain")
        self.add_field("blue_gain", "Blue gain")
        self.add_field("crf", "CRF")
        self.add_field("preset", "Encoding preset")
        for key in ("red_gain", "green_gain", "blue_gain"):
            self.controls[key].setToolTip(
                "0–2; 1 is neutral. Below 1 reduces this channel; above 1 increases it. "
                "High gains may amplify noise or clip highlights."
            )
