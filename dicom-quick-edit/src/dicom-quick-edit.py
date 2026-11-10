# Author: Tucker Netherton, PhD,  with assistance GPT-6-sol, all code proof read and modified
"""Single-file DICOM metadata editor. No image decoding or de-identification."""
import os
import sys
import tempfile
from pathlib import Path

import pydicom
from pydicom import config
from pydicom.dataelem import DataElement
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

# Restrict edits to textual and ordinary numeric VRs. Other VRs, file meta,
# and sequences are displayed but cannot be changed in this tool.
EDITABLE_VRS = {
    "AE", "AS", "CS", "DA", "DS", "DT", "IS", "LO", "LT", "PN",
    "SH", "ST", "TM", "UC", "UI", "UR", "UT",
    "FL", "FD", "SL", "SS", "UL", "US",
}
INTEGER_VRS = {"SL", "SS", "UL", "US"}
FLOAT_VRS = {"FL", "FD"}
MULTILINE_VRS = {"LT", "ST", "UT", "UC", "UR"}


def display_value(element):
    """Format an element's value for the metadata tree."""
    if element.VR == "SQ":
        return f"{len(element.value)} item(s)"
    if element.VR not in EDITABLE_VRS:
        return "(not editable)"
    value = element.value
    if isinstance(value, (list, tuple, pydicom.multival.MultiValue)):
        return " \\ ".join(str(part) for part in value)
    return str(value) if value is not None else ""


def converted_value(element, text):
    """Validate without changing the loaded dataset."""
    if element.VR not in EDITABLE_VRS:
        raise ValueError("This value representation is read-only.")
    # A backslash separates DICOM values, except in long/free-text VRs.
    parts = [text] if element.VR in MULTILINE_VRS else text.split("\\")
    if element.VR in INTEGER_VRS:
        value = [int(part) for part in parts] if text else ""
    elif element.VR in FLOAT_VRS:
        value = [float(part) for part in parts] if text else ""
    else:
        value = parts if len(parts) > 1 else parts[0]
    if isinstance(value, list) and len(value) == 1:
        value = value[0]
    candidate = DataElement(element.tag, element.VR, value, validation_mode=config.RAISE)
    return candidate.value


class DicomQuickEdit(QWidget):
    def __init__(self):
        """Initialize the editor window and its file, metadata, and save controls."""
        super().__init__()
        self.setWindowTitle("DICOM Quick Edit")
        self.resize(950, 650)
        self.setAcceptDrops(True)
        self.path = None
        self.dataset = None
        self.changed = False

        layout = QVBoxLayout(self)
        self.file_label = QLabel("Open a .dcm file, or drag and drop one here.")
        self.file_label.setWordWrap(True)
        layout.addWidget(self.file_label)

        open_button = QPushButton("Browse for DICOM file")
        open_button.clicked.connect(self.browse)
        layout.addWidget(open_button)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter metadata by tag, name, VR, or value")
        self.search.textChanged.connect(self.filter_tree)
        layout.addWidget(self.search)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Tag", "Name", "VR", "Value"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setColumnWidth(0, 120)
        self.tree.setColumnWidth(1, 290)
        self.tree.setColumnWidth(2, 55)
        self.tree.currentItemChanged.connect(self.select_item)
        layout.addWidget(self.tree)

        self.selection_label = QLabel("Select a field to edit. Sequences and binary data are read-only.")
        layout.addWidget(self.selection_label)
        self.entry = QLineEdit()
        self.entry.setPlaceholderText("New value (use \\ between multiple DICOM values)")
        self.entry.setEnabled(False)
        self.entry.returnPressed.connect(self.apply_edit)
        layout.addWidget(self.entry)

        apply_button = QPushButton("Apply field change")
        apply_button.clicked.connect(self.apply_edit)
        self.apply_button = apply_button
        apply_button.setEnabled(False)
        layout.addWidget(apply_button)

        buttons = QHBoxLayout()
        self.save_button = QPushButton("Save (replace original)")
        self.save_button.clicked.connect(lambda: self.save(False))
        self.save_button.setEnabled(False)
        buttons.addWidget(self.save_button)
        self.save_as_button = QPushButton("Save as new file (same folder)")
        self.save_as_button.clicked.connect(lambda: self.save(True))
        self.save_as_button.setEnabled(False)
        buttons.addWidget(self.save_as_button)
        layout.addLayout(buttons)

        self.status = QLabel("No file loaded.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

    def browse(self):
        """Prompt for a DICOM file and load it when one is selected."""
        start = str(self.path.parent) if self.path else ""
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open DICOM file", start, "DICOM files (*.dcm *.DCM);;All files (*)"
        )
        if filename:
            self.load_file(Path(filename))

    def dragEnterEvent(self, event):
        """Accept a drag only when it contains one local DICOM file."""
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        if len(urls) == 1 and urls[0].isLocalFile() and urls[0].toLocalFile().lower().endswith(".dcm"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        """Load a dropped local DICOM file."""
        filename = event.mimeData().urls()[0].toLocalFile()
        self.load_file(Path(filename))
        event.acceptProposedAction()

    def confirm_discard(self):
        """Ask whether to discard applied edits that have not been saved."""
        if not self.changed:
            return True
        reply = QMessageBox.question(
            self, "Unsaved changes", "Discard the applied but unsaved changes?",
            QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Cancel
        )
        return reply == QMessageBox.Discard

    def load_file(self, path):
        """Read a DICOM file and populate the metadata tree."""
        if not self.confirm_discard():
            return
        if path.suffix.lower() != ".dcm" or not path.is_file():
            QMessageBox.warning(self, "Invalid file", "Choose an existing .dcm file.")
            return
        try:
            dataset = pydicom.dcmread(str(path))
        except Exception as exc:
            QMessageBox.critical(self, "Cannot open DICOM", str(exc))
            return
        self.dataset = dataset
        self.path = path.resolve()
        self.changed = False
        self.search.clear()
        self.tree.clear()
        self.entry.clear()
        if dataset.file_meta:
            meta_root = QTreeWidgetItem(self.tree, ["", "File meta (read-only)", "", ""])
            for element in dataset.file_meta:
                self.add_element(meta_root, element, False)
        for element in dataset:
            self.add_element(self.tree, element, True)
        self.tree.setEnabled(True)
        self.update_buttons()
        self.file_label.setText(str(self.path))
        self.status.setText("Loaded. Select a field, enter a new value, then Apply field change.")

    def add_element(self, parent, element, editable):
        """Add an element and any nested sequence items to the tree."""
        item = QTreeWidgetItem(parent, [
            str(element.tag), element.name, element.VR, display_value(element)
        ])
        if editable and element.VR in EDITABLE_VRS:
            item.setData(0, Qt.UserRole, element)
        if element.VR == "SQ":
            for index, dataset in enumerate(element.value, 1):
                child = QTreeWidgetItem(item, ["", f"Item {index}", "", ""])
                for nested in dataset:
                    self.add_element(child, nested, editable)

    def select_item(self, current, previous):
        """Populate and enable the value editor for an editable selection."""
        element = current.data(0, Qt.UserRole) if current else None
        enabled = element is not None
        self.entry.setEnabled(enabled)
        self.apply_button.setEnabled(enabled)
        self.entry.setText(display_value(element) if enabled else "")
        self.selection_label.setText(
            f"{element.tag} {element.name} ({element.VR})"
            if enabled else "Read-only field. Select a textual or numeric metadata value to edit."
        )

    def filter_tree(self, query):
        """Show metadata rows matching the search query or containing matches."""
        query = query.casefold().strip()

        def show_matches(item):
            """Update visibility recursively and report whether an item matches."""
            own_match = any(query in item.text(col).casefold() for col in range(4))
            child_match = any(show_matches(item.child(i)) for i in range(item.childCount()))
            visible = not query or own_match or child_match
            item.setHidden(not visible)
            if query and child_match:
                item.setExpanded(True)
            return visible

        for index in range(self.tree.topLevelItemCount()):
            show_matches(self.tree.topLevelItem(index))

    def apply_edit(self):
        """Validate and apply the entered value to the loaded dataset."""
        item = self.tree.currentItem()
        element = item.data(0, Qt.UserRole) if item else None
        if element is None:
            return
        try:
            new_value = converted_value(element, self.entry.text())
            if element.tag == 0x00080016 and self.dataset.file_meta:
                # SOP Class UID is duplicated in the file meta header.
                self.dataset.file_meta.MediaStorageSOPClassUID = new_value
            elif element.tag == 0x00080018 and self.dataset.file_meta:
                # SOP Instance UID is duplicated in the file meta header.
                self.dataset.file_meta.MediaStorageSOPInstanceUID = new_value
            element.value = new_value
        except (ValueError, TypeError, OverflowError) as exc:
            QMessageBox.warning(self, "Invalid value", str(exc))
            return
        item.setText(3, display_value(element))
        self.entry.setText(display_value(element))
        self.changed = True
        self.update_buttons()
        self.status.setText("Change applied in memory; save to write the file.")
        # Refresh the file-meta view if a UID was changed.
        if element.tag in (0x00080016, 0x00080018):
            root = self.tree.topLevelItem(0)
            if root and root.text(1) == "File meta (read-only)":
                for index in range(root.childCount()):
                    child = root.child(index)
                    tag = child.text(0)
                    if tag in ("(0002, 0002)", "(0002, 0003)"):
                        meta_tag = int(tag[1:5] + tag[7:11], 16)
                        child.setText(3, display_value(self.dataset.file_meta[meta_tag]))

    def update_buttons(self):
        """Enable save actions only when the loaded dataset has applied edits."""
        enabled = self.dataset is not None and self.changed
        self.save_button.setEnabled(enabled)
        self.save_as_button.setEnabled(enabled)

    def save(self, as_new):
        """Write the edited dataset beside the original or replace the original."""
        if self.dataset is None or self.path is None or not self.changed:
            return
        destination = self.path
        if as_new:
            suggested = self.path.stem + "_edited.dcm"
            name, ok = QInputDialog.getText(
                self, "Save as new file", "Filename in the source folder:", text=suggested
            )
            if not ok:
                return
            name = name.strip()
            if not name or name in (".", "..") or Path(name).name != name or "/" in name or "\\" in name or not name.lower().endswith(".dcm"):
                QMessageBox.warning(self, "Invalid filename", "Enter a .dcm filename, not a path.")
                return
            destination = self.path.parent / name
        if destination.exists():
            action = "original file" if destination == self.path else "existing file"
            reply = QMessageBox.question(
                self, "Confirm overwrite", f"Replace the {action}?\n{destination}",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        temporary = None
        try:
            fd, temporary = tempfile.mkstemp(prefix=".dicom-quick-edit-", suffix=".dcm", dir=str(self.path.parent))
            os.close(fd)
            self.dataset.save_as(temporary, write_like_original=True)
            if destination.exists():
                os.chmod(temporary, destination.stat().st_mode)
            os.replace(temporary, destination)
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", f"File was not replaced:\n{exc}")
            return
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)
        self.changed = False
        self.update_buttons()
        self.status.setText(f"Saved: {destination}")
        if as_new:
            self.path = destination.resolve()
            self.file_label.setText(str(self.path))

    def closeEvent(self, event):
        """Confirm whether the window may close when edits remain unsaved."""
        if self.confirm_discard():
            event.accept()
        else:
            event.ignore()


def main():
    """Start the DICOM quick-edit desktop application."""
    app = QApplication(sys.argv)
    window = DicomQuickEdit()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()