"""Shared visual styling for the contour comparison window and dialogs.

Uses the DICOM viewer's light palette, blue controls, and restrained borders.
No additional GUI packages are needed beyond PyQt5.
"""

APP_STYLE = """
QWidget {
    color: #1f2933;
    font-size: 13px;
}
QWidget#contourRoot, QWidget#sidebar, QWidget#workspace, QDialog {
    background-color: #f5f7fb;
}
QGroupBox {
    background-color: #ffffff;
    border: 1px solid #ccd6e0;
    border-radius: 8px;
    margin-top: 14px;
    padding: 12px 10px 10px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 5px;
    color: #1f2933;
}
QPushButton {
    background-color: #1976d2;
    color: #ffffff;
    border: none;
    border-radius: 5px;
    padding: 9px 12px;
    font-weight: 600;
    min-height: 20px;
}
QPushButton:hover { background-color: #1565c0; }
QPushButton:pressed { background-color: #0d47a1; }
QPushButton:disabled { background-color: #aeb8c2; }
QLineEdit, QTextEdit, QListWidget, QTableWidget, QComboBox {
    background-color: #ffffff;
    border: 1px solid #cbd5df;
    border-radius: 5px;
    padding: 5px;
    selection-background-color: #d8eaff;
    selection-color: #1f2933;
}
QLineEdit:read-only { color: #52616f; }
QListWidget::item, QTableWidget::item { padding: 5px; }
QListWidget::item:selected, QTableWidget::item:selected {
    background-color: #d8eaff;
    color: #1f2933;
}
QHeaderView::section {
    background-color: #eaf0f6;
    color: #1f2933;
    border: none;
    border-bottom: 1px solid #ccd6e0;
    padding: 8px;
    font-weight: 600;
}
QCheckBox { spacing: 8px; }
QProgressBar {
    background-color: #e5ebf2;
    border: 1px solid #cbd5df;
    border-radius: 5px;
    text-align: center;
    min-height: 20px;
}
QProgressBar::chunk {
    background-color: #1976d2;
    border-radius: 4px;
}
QScrollArea {
    border: none;
    background-color: transparent;
}
QSplitter::handle { background-color: #e2e8ef; }
"""