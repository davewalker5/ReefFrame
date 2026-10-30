"""Dedicated gif parameter layout."""

from PySide6.QtWidgets import QWidget

from gui.dialogs.base_operation_dialog import BaseOperationDialog


class GifDialog(BaseOperationDialog):
    """Configure the gif operation."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """
        Initialise operation-specific defaults and controls.

        :param parent: Optional parent widget controlling dialog ownership.
        """
        super().__init__("gif", parent)

    def build_parameters(self) -> None:
        """Lay out the labelled gif parameters."""
        self.add_field("fps", "Frames per second")
        self.add_field("width", "Width (aspect ratio preserved)")
        self.add_field("colors", "Palette colors")
        self.add_field("dither", "Dithering")
        self.add_field("loop", "Loop count (-1 none, 0 infinite)")
