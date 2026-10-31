"""Desktop entry point for ReefFrame."""

import logging
import sys
from importlib.resources import files

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from config.settings import log_directory, migrate_user_settings
from gui.main_window import MainWindow


def main() -> int:
    """
    Initialise persistent logging, application identity, and the main window.

    :return: Application event-loop exit code, zero for a normal exit.
    """
    application = QApplication(sys.argv)
    application.setApplicationName("ReefFrame")
    application.setOrganizationName("ReefFrame")
    migrate_user_settings()
    directory = log_directory()
    directory.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=directory / "reefframe.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    application.setWindowIcon(QIcon(str(files("resources").joinpath("reefframe.png"))))
    application.setStyle("Fusion")
    window = MainWindow()
    application.aboutToQuit.connect(window.shutdown)
    window.show()
    try:
        return application.exec()
    finally:
        # Destroy Qt-owned widgets before Shiboken/Python's interpreter cleanup.
        # Signal callbacks can otherwise retain buttons until Qt has shut down.
        window.shutdown()
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


if __name__ == "__main__":
    sys.exit(main())
