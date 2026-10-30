"""Dedicated reduce parameter layout."""

from PySide6.QtWidgets import QWidget

from gui.dialogs.base_operation_dialog import BaseOperationDialog


class ReduceDialog(BaseOperationDialog):
    """Configure the reduce operation."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """
        Initialise operation-specific defaults and controls.

        :param parent: Optional parent widget controlling dialog ownership.
        """
        super().__init__("reduce", parent)

    def build_parameters(self) -> None:
        """Lay out the labelled reduce parameters."""
        self.add_field("crf", "CRF")
        self.add_field("preset", "Encoding preset")
        self.add_field("audio_policy", "Audio policy")
