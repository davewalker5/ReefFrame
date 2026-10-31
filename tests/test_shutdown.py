"""Exercise actual interpreter teardown, where shutdown crashes occur."""

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("active_worker", [False, True])
def test_clean_application_quit(tmp_path, active_worker):
    """
    Quitting exits normally, even when a worker must first be cancelled.

    :param tmp_path: Isolated temporary directory supplied by pytest.
    :param active_worker: Whether to start a cancellable worker before requesting application quit.
    """
    script = """
import sys
from pathlib import Path
from PySide6.QtCore import QTimer, QThread
from PySide6.QtWidgets import QApplication
import main
import gui.main_window as gui

application = QApplication([])
main.QApplication = lambda arguments: application
main.log_directory = lambda: Path(sys.argv[1]) / "logs"
main.migrate_user_settings = lambda: None
gui.user_directory = lambda: Path(sys.argv[1])
original_init = gui.MainWindow.__init__
gui.MainWindow.check_dependencies = lambda self: None

class WaitingWorker(QThread):
    def run(self):
        '''Wait until the test requests interruption.'''
        while not self.isInterruptionRequested():
            self.msleep(10)

class Runner:
    def __init__(self, worker):
        '''Initialise cancellation forwarding.

        :param worker: Test thread interrupted by cancellation.
        '''
        self.worker = worker
    def cancel(self):
        '''Request interruption of the test worker.'''
        self.worker.requestInterruption()

def initialise(self):
    '''Initialise the window and optional cancellable test worker.'''
    original_init(self)
    if sys.argv[2] == "True":
        self.worker = WaitingWorker()
        self.runner = Runner(self.worker)
        self.worker.finished.connect(self.batch_finished)
        self.worker.start()

gui.MainWindow.__init__ = initialise
QTimer.singleShot(50, application.quit)
sys.exit(main.main())
"""
    environment = os.environ | {
        "QT_QPA_PLATFORM": "offscreen",
        "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
    }
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path), str(active_worker)],
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert "QThread: Destroyed" not in result.stderr
