"""Mirror Python console output into the contour comparison activity pane."""

import sys
from contextlib import contextmanager

from PyQt5.QtCore import QObject, QThread, pyqtSignal
from PyQt5.QtWidgets import QApplication


class ConsoleTee(QObject):
    """Preserve terminal output while forwarding complete lines to the GUI."""

    output = pyqtSignal(str)

    def __init__(self, stream, parent=None):
        super().__init__(parent)
        self.stream = stream
        self.buffer = ""
        self._processing_events = False

    def write(self, text):
        self.stream.write(text)
        self.buffer += text
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            self.output.emit(line)
            # Conversion runs on the GUI thread; allow the activity pane to
            # repaint between its progress messages without changing conversion.
            app = QApplication.instance()
            if app is not None and QThread.currentThread() == self.thread() and not self._processing_events:
                self._processing_events = True
                try:
                    app.processEvents()
                finally:
                    self._processing_events = False
        return len(text)

    def flush(self):
        self.stream.flush()
        if self.buffer:
            self.output.emit(self.buffer)
            self.buffer = ""

    def isatty(self):
        return self.stream.isatty()

    def fileno(self):
        return self.stream.fileno()

    @property
    def encoding(self):
        return self.stream.encoding


@contextmanager
def mirror_console(window):
    """Redirect Python stdout/stderr for the life of the GUI, then restore both."""
    stdout, stderr = sys.stdout, sys.stderr
    output = ConsoleTee(stdout, window)
    errors = ConsoleTee(stderr, window)
    output.output.connect(window.append_console_line)
    errors.output.connect(window.append_console_line)
    sys.stdout, sys.stderr = output, errors
    try:
        yield
    finally:
        sys.stdout, sys.stderr = stdout, stderr
        output.flush()
        errors.flush()