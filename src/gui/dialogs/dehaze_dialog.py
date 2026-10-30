"""Dedicated dehaze parameter layout."""

from PySide6.QtWidgets import QWidget

from gui.dialogs.base_operation_dialog import BaseOperationDialog


class DehazeDialog(BaseOperationDialog):
    """Configure the dehaze operation."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """
        Initialise operation-specific defaults and controls.

        :param parent: Optional parent widget controlling dialog ownership.
        """
        super().__init__("dehaze", parent)

    def build_parameters(self) -> None:
        """Lay out the labelled dehaze parameters."""
        self.add_field("contrast", "Contrast")
        self.add_field("brightness", "Brightness")
        self.add_field("crf", "CRF")
        self.add_field("preset", "Encoding preset")
