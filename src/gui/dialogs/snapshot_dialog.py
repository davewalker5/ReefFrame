"""Dedicated snapshot parameter layout."""

from PySide6.QtWidgets import QWidget

from gui.dialogs.base_operation_dialog import BaseOperationDialog


class SnapshotDialog(BaseOperationDialog):
    """Configure the snapshot operation."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """
        Initialise operation-specific defaults and controls.

        :param parent: Optional parent widget controlling dialog ownership.
        """
        super().__init__("snapshot", parent)

    def build_parameters(self) -> None:
        """Lay out the labelled snapshot parameters."""
        self.add_field("timestamp", "Timestamp HH:MM:SS[.fraction]")
        self.add_field("image_type", "Image type")
