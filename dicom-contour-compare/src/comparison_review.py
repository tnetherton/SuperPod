"""Modal review of comparison pairs before any metrics are calculated."""

import os

import pandas as pd
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QLabel,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from comparison_workflow import COMPARISON_COLUMNS
from contour_style import APP_STYLE


class ComparisonReviewDialog(QDialog):
    """Allow exclusion of pairs and ground-truth selection on each remaining row."""

    def __init__(self, comparisons, parent=None):
        super().__init__(parent)
        self.comparisons = comparisons.reset_index(drop=True)
        self.approved = None
        self.setWindowTitle("Review contour comparisons")
        self.resize(1150, 500)
        self.setStyleSheet(APP_STYLE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        heading = QLabel("Review comparison pairs", self)
        heading.setStyleSheet("font-size: 17px; font-weight: 700; color: #1f2933;")
        layout.addWidget(heading)
        note = QLabel(
            "Check the pairs to compare and choose the ground truth for each pair. "
            "Metrics will not run until you confirm."
        )
        note.setStyleSheet("color: #52616f;")
        layout.addWidget(note)
        self.table = QTableWidget(len(self.comparisons), 8, self)
        self.table.setHorizontalHeaderLabels([
            "Run", "Contour 1", "Contour 2", "Ground truth",
            "Struct name 1", "Struct name 2", "Mask path 1", "Mask path 2",
        ])
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.ground_truth = []
        for index, row in self.comparisons.iterrows():
            run = QTableWidgetItem()
            run.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            run.setCheckState(Qt.Checked)
            self.table.setItem(index, 0, run)
            for column, field in (
                (1, "contour_name_1"), (2, "contour_name_2"),
                (4, "structure_file_1"), (5, "structure_file_2"),
                (6, "path_1"), (7, "path_2"),
            ):
                value = os.path.basename(row[field]) if field.startswith("structure_file") else row[field]
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(row[field]))
                self.table.setItem(index, column, item)
            choice = QComboBox(self.table)
            choice.addItems(["Contour 1", "Contour 2"])
            choice.setCurrentIndex(int(row["ground_truth"]) - 1)
            self.table.setCellWidget(index, 3, choice)
            self.ground_truth.append(choice)
        layout.addWidget(self.table)
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(6, 220)
        self.table.setColumnWidth(7, 220)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        rows = []
        for index, row in self.comparisons.iterrows():
            if self.table.item(index, 0).checkState() == Qt.Checked:
                updated = row.to_dict()
                updated["ground_truth"] = self.ground_truth[index].currentIndex() + 1
                rows.append(updated)
        self.approved = pd.DataFrame(rows, columns=COMPARISON_COLUMNS)
        super().accept()