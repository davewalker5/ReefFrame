"""Dedicated stabilise parameter layout."""

from PySide6.QtWidgets import QWidget

from gui.dialogs.base_operation_dialog import BaseOperationDialog


class StabiliseDialog(BaseOperationDialog):
    """Configure the stabilise operation."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """
        Initialise operation-specific defaults and controls.

        :param parent: Optional parent widget controlling dialog ownership.
        """
        super().__init__("stabilise", parent)

    def build_parameters(self) -> None:
        """Lay out the labelled stabilise parameters."""
        self.add_field("shakiness", "Shakiness")
        self.add_field("accuracy", "Detection accuracy")
        self.add_field("smoothing", "Smoothing radius (frames)")
        self.add_field("optzoom", "Automatic zoom")
        self.add_field("crf", "CRF")
        self.add_field("preset", "Encoding preset")
        self.add_field("keep_motion", "Retain motion data (.trf)")
