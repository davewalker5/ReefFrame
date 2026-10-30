"""Dedicated enhance parameter layout."""

from PySide6.QtWidgets import QWidget

from gui.dialogs.base_operation_dialog import BaseOperationDialog


class EnhanceDialog(BaseOperationDialog):
    """Configure the enhance operation."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """
        Initialise operation-specific defaults and controls.

        :param parent: Optional parent widget controlling dialog ownership.
        """
        super().__init__("enhance", parent)

    def build_parameters(self) -> None:
        """Lay out the labelled enhance parameters."""
        self.add_field("contrast", "First-stage contrast")
        self.add_field("brightness", "First-stage brightness")
        self.add_field("second_contrast", "Second-stage contrast")
        self.add_field("vibrance", "Vibrance")
        self.add_field("crf", "CRF")
        self.add_field("preset", "Encoding preset")
