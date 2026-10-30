"""Dedicated convert parameter layout."""

from PySide6.QtWidgets import QWidget

from gui.dialogs.base_operation_dialog import BaseOperationDialog


class ConvertDialog(BaseOperationDialog):
    """Configure the convert operation."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """
        Initialise operation-specific defaults and controls.

        :param parent: Optional parent widget controlling dialog ownership.
        """
        super().__init__("convert", parent)

    def build_parameters(self) -> None:
        """Lay out the labelled convert parameters."""
        self.add_field("codec", "Video codec")
        self.add_field("preset", "Encoding preset")
        self.add_field("crf", "CRF (lower = higher quality)")
        self.add_field("pixel_format", "Pixel format")
        self.add_field("audio_codec", "Audio codec")
        self.add_field("audio_bitrate", "Audio bitrate")
