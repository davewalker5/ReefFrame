"""Dedicated gamma correction controls."""

from PySide6.QtWidgets import QWidget

from gui.dialogs.base_operation_dialog import BaseOperationDialog


class GammaDialog(BaseOperationDialog):
    """Configure independent gamma correction."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise correction controls.

        :param parent: Optional owning widget.
        """
        super().__init__("gamma", parent)

    def build_parameters(self) -> None:
        """Add correction and encoding controls."""
        self.add_field("gamma", "Gamma (above 1 lightens midtones)")
        self.add_field("shadow_lift", "Shadow lift")
        self.add_field("shadow_range", "Shadow range")
        self.add_field("crf", "CRF")
        self.add_field("preset", "Encoding preset")
        self.controls["gamma"].setToolTip(
            "0.1–3.0; 1 is neutral. Above 1 lightens midtones; below 1 darkens them."
        )
        self.controls["shadow_lift"].setToolTip(
            "0–0.5; 0 disables lifting. Higher values raise dark tones more strongly. "
            "Existing shadow noise may become more visible."
        )
        self.controls["shadow_range"].setToolTip(
            "0.05–1.0; fraction of the tonal range affected, starting at black. "
            "The lift fades smoothly to zero at this boundary."
        )
