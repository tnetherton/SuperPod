import sys
import os
import pydicom
import pandas as pd
from PyQt5.QtWidgets import QApplication, QWidget, QGroupBox, QPushButton, QVBoxLayout, QFileDialog, QTextEdit, QProgressBar, QScrollArea, QDialog, QFormLayout, QListWidget, QHBoxLayout, QListWidgetItem, QLabel, QMessageBox, QLineEdit, QSplitter
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor
from dcmrtstruct2nii import dcmrtstruct2nii  # Import the dcmrtstruct2nii Python API
from comparison_workflow import selected_dicom_log, build_comparison_list, calculate_metrics
from comparison_review import ComparisonReviewDialog
from comparison_figures import plot_comparison
from contour_style import APP_STYLE
from console_output import mirror_console

class SelectRSFilesDialog(QDialog):
    def __init__(self, dicom_log, parent=None):
        super().__init__(parent)
        
        self.setWindowTitle("Select Contours")
        self.resize(680, 500)
        self.setStyleSheet(APP_STYLE)

        # Create layout
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        heading = QLabel("Choose contours to convert")
        heading.setStyleSheet("font-size: 17px; font-weight: 700; color: #1f2933;")
        layout.addWidget(heading)
        note = QLabel("Select one or more ROIs. Each item shows its source RTSTRUCT.")
        note.setStyleSheet("color: #52616f;")
        layout.addWidget(note)

        # Create a scrollable area to hold the list widget
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        
        # Create a list widget to display DICOM structure names
        self.list_widget = QListWidget(self)
        self.list_widget.setSelectionMode(QListWidget.MultiSelection)
        
        # Grouping by RS file and coloring rows
        self.rs_file_dict = {}
        
        # Populate the list widget with structure names and color code the background
        dicom_log = dicom_log[dicom_log['Modality']=='RTSTRUCT']
        for _, row in dicom_log.iterrows():
            structure_names = row['StructureNames'].split(", ")
            rs_file_name = row['FileName']
            
            # Sort structure names alphabetically
            structure_names.sort()

            # Store in a dictionary by RS file name
            if rs_file_name not in self.rs_file_dict:
                self.rs_file_dict[rs_file_name] = []

            self.rs_file_dict[rs_file_name].extend(structure_names)
        
        # Add items to the list widget with color coding
        colors = [QColor("white"), QColor("lightgray")]  # Define white and gray colors
        color_index = 0  # Used to alternate colors
        
        for rs_file, structure_names in self.rs_file_dict.items():
            for structure in structure_names:
                item = QListWidgetItem(f"{structure} ({rs_file})")  # Add RS file name in parentheses next to structure
                item.setBackground(colors[color_index])  # Alternate between white and gray
                item.setData(Qt.UserRole, rs_file)  # Attach the RS file to each item
                self.list_widget.addItem(item)  # Add item to list widget
                color_index = 1 - color_index  # Toggle color index between 0 and 1
        
        # Add the list widget inside the scrollable area
        self.scroll_area.setWidget(self.list_widget)
        
        # Add the scroll area to the layout
        layout.addWidget(self.scroll_area)

        # Add the "Select" and "Cancel" buttons
        button_layout = QHBoxLayout()
        self.select_button = QPushButton("Select", self)
        self.select_button.clicked.connect(self.select_files)
        button_layout.addWidget(self.select_button)

        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)
        
        # Set the dialog layout
        self.setLayout(layout)

    def select_files(self):
        """Get selected files and close the dialog"""
        selected_items = self.list_widget.selectedItems()
        selected_files = [item.text() for item in selected_items]
        
        # Send selected files back to the parent window or handle them here
        self.selected_files = selected_files
        self.accept()  # Close the dialog

import os
import shutil
from dcmrtstruct2nii import dcmrtstruct2nii  # Assuming this is already properly installed and imported

class ContourComparisonApp(QWidget):
    def __init__(self):
        super().__init__()

        # Initialize the GUI components
        self.setWindowTitle("Quantitative Contour Comparison")
        self.setObjectName("contourRoot")
        self.resize(1150, 720)
        self.setMinimumSize(900, 560)
        self.setStyleSheet(APP_STYLE)

        # Directories for DICOM and temporary files
        self.dicom_dir = ""
        self.temp_dir = ""

        # Log for DICOM files and structure information
        self.dicom_log = pd.DataFrame(columns=['FileName', 'Path', 'Modality', 'StructureNames', 'selected'])

        # DICOM viewer-inspired control rail and spacious results pane.
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(16, 14, 16, 16)
        self.layout.setSpacing(12)
        header = QHBoxLayout()
        self.title_label = QLabel("Quantitative Contour Comparison", self)
        self.title_label.setStyleSheet("font-size: 21px; font-weight: 700; color: #1f2933;")
        header.addWidget(self.title_label)
        header.addStretch()
        self.layout.addLayout(header)

        splitter = QSplitter(Qt.Horizontal, self)
        sidebar = QWidget(self)
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(300)
        sidebar.setMaximumWidth(430)
        controls = QVBoxLayout(sidebar)
        controls.setContentsMargins(4, 0, 12, 0)
        controls.setSpacing(10)

        input_group = QGroupBox("Input", sidebar)
        input_layout = QVBoxLayout(input_group)
        input_layout.setSpacing(8)
        self.dicom_button = QPushButton("Select DICOM Directory", self)
        self.dicom_button.clicked.connect(self.select_dicom_directory)
        input_layout.addWidget(self.dicom_button)
        self.dicom_path_display = QLineEdit(self)
        self.dicom_path_display.setReadOnly(True)
        self.dicom_path_display.setPlaceholderText("No DICOM directory selected")
        input_layout.addWidget(self.dicom_path_display)
        self.temp_button = QPushButton("Select Temporary Directory", self)
        self.temp_button.clicked.connect(self.select_temp_directory)
        input_layout.addWidget(self.temp_button)
        self.temp_path_display = QLineEdit(self)
        self.temp_path_display.setReadOnly(True)
        self.temp_path_display.setPlaceholderText("No output directory selected")
        input_layout.addWidget(self.temp_path_display)
        controls.addWidget(input_group)

        workflow_group = QGroupBox("Workflow", sidebar)
        workflow_layout = QVBoxLayout(workflow_group)
        workflow_layout.setSpacing(8)
        self.parse_button = QPushButton("Parse DICOM Files", self)
        self.parse_button.clicked.connect(self.parse_dicom_files)
        workflow_layout.addWidget(self.parse_button)
        self.select_contours_button = QPushButton("Select Contours", self)
        self.select_contours_button.clicked.connect(self.select_contours)
        workflow_layout.addWidget(self.select_contours_button)
        controls.addWidget(workflow_group)

        progress_group = QGroupBox("Progress", sidebar)
        progress_layout = QVBoxLayout(progress_group)
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        progress_layout.addWidget(self.progress_bar)
        controls.addWidget(progress_group)
        controls.addStretch(1)
        splitter.addWidget(sidebar)

        workspace = QWidget(self)
        workspace.setObjectName("workspace")
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(8, 0, 0, 0)
        workspace_layout.setSpacing(8)
        results_group = QGroupBox("DICOM log & activity", workspace)
        results_layout = QVBoxLayout(results_group)
        self.metadata_summary = QTextEdit(self)
        self.metadata_summary.setReadOnly(True)
        self.metadata_summary.setMaximumHeight(140)
        self.metadata_summary.setStyleSheet("font-family: monospace;")
        results_layout.addWidget(self.metadata_summary)
        self.metadata_display = QTextEdit(self)
        self.metadata_display.setReadOnly(True)
        self.metadata_display.setPlaceholderText("Select your DICOM and output directories to begin.")
        self.metadata_display.setStyleSheet("font-family: monospace;")
        results_layout.addWidget(self.metadata_display)
        workspace_layout.addWidget(results_group)
        splitter.addWidget(workspace)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([350, 780])
        self.layout.addWidget(splitter)

    def button_style(self):
        """Returns the style for buttons"""
        return (
            "QPushButton {"
            "background-color: #2196F3; color: white; padding: 10px; border-radius: 5px; font-size: 16px;"
            "border: none; margin-bottom: 10px;} "
            "QPushButton:hover {background-color: #1976D2;} "
            "QPushButton:pressed {background-color: #1565C0;}"
        )

    def select_dicom_directory(self):
        """Select DICOM directory"""
        self.dicom_dir = QFileDialog.getExistingDirectory(self, "Select DICOM Directory")
        if self.dicom_dir:
            self.dicom_path_display.setText(self.dicom_dir)
            self.dicom_path_display.setToolTip(self.dicom_dir)
            self.dicom_button.setStyleSheet(self.green_button_style())
            self.display_metadata()

    def select_temp_directory(self):
        """Select temporary directory"""
        self.temp_dir = QFileDialog.getExistingDirectory(self, "Select Temporary Directory")
        if self.temp_dir:
            self.temp_path_display.setText(self.temp_dir)
            self.temp_path_display.setToolTip(self.temp_dir)
            self.temp_button.setStyleSheet(self.green_button_style())
            self.display_metadata()

    def parse_dicom_files(self):
        """Parse DICOM files and log RS structure names"""
        if not self.dicom_dir:
            return

        dicom_files = [f for f in os.listdir(self.dicom_dir) if f.lower().endswith('.dcm')]

        self.dicom_log = pd.DataFrame(columns=['FileName', 'Path', 'Modality', 'StructureNames', 'selected'])

        # Set the progress bar to zero and make it visible
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(len(dicom_files))  # Set the maximum value to the number of DICOM files

        # Parse the DICOM files and log the structure names
        for index, dicom_file in enumerate(dicom_files):
            dicom_path = os.path.join(self.dicom_dir, dicom_file)
            dicom_data = pydicom.dcmread(dicom_path)

            modality = dicom_data.Modality
            structure_names = self.extract_structure_names(dicom_data)

            self.dicom_log = pd.concat([self.dicom_log, pd.DataFrame([{
                'FileName': dicom_file,
                'Path': os.path.abspath(dicom_path),
                'Modality': modality,
                'StructureNames': ', '.join(structure_names),
                'selected': ''
            }])], ignore_index=True)

            # Update progress bar after processing each file
            self.progress_bar.setValue(index + 1)  # Increment progress bar

            # Optional: Update metadata display (if desired, or just after completion)
            self.display_metadata()

        # Save log to temporary directory
        if self.temp_dir:
            log_file = os.path.join(self.temp_dir, "dicom_log.csv")
            self.dicom_log.to_csv(log_file, index=False)

        self.display_metadata()

        # Turn the "Parse DICOM Files" button green after parsing
        self.parse_button.setStyleSheet(self.green_button_style())

        # Optional: Reset progress bar when done
        self.progress_bar.setValue(0)

    def extract_structure_names(self, dicom_data):
        """Extract structure names from RTSTRUCT"""
        if 'RTSTRUCT' in dicom_data.Modality:
            structures = dicom_data.StructureSetROISequence
            return [structure.ROIName for structure in structures]
        return []

    def select_contours(self):
        """Let user select contours from the DICOM log and update the log with selected contours"""
        if self.dicom_log.empty:
            return

        # Open the RS file selection dialog
        dialog = SelectRSFilesDialog(self.dicom_log, self)
        dialog.exec_()

        # After dialog closes, do something with the selected RS files
        if hasattr(dialog, 'selected_files'):
            selected_files = dialog.selected_files
            print("Selected RS Files:", selected_files)

            if not self.temp_dir:
                QMessageBox.warning(self, "Output directory required",
                                    "Select a temporary directory before converting.")
                return

            # Store only selected structures on selected RTSTRUCTs.
            updated_log = self.dicom_log.copy()
            selected_set = set(selected_files)
            updated_log['selected'] = updated_log.apply(
                lambda row: ", ".join(
                    structure for structure in row['StructureNames'].split(", ")
                    if row['Modality'] == 'RTSTRUCT'
                    and f"{structure} ({row['FileName']})" in selected_set
                ),
                axis=1
            )
            try:
                self.dicom_log_updated = selected_dicom_log(updated_log)
            except (ValueError, OSError, pydicom.errors.InvalidDicomError) as exc:
                QMessageBox.warning(self, "Cannot pair CT and RTSTRUCT", str(exc))
                return

            self.dicom_log_updated.to_csv(
                os.path.join(self.temp_dir, "dicom_log_updated.csv"), index=False
            )
            self.select_contours_button.setStyleSheet(self.green_button_style())
            self.create_subdirectories_and_convert()

            comparisons = build_comparison_list(self.dicom_log_updated, self.temp_dir)
            if comparisons.empty:
                QMessageBox.information(self, "No comparisons",
                                        "Select at least two contours to compare.")
                return
            review = ComparisonReviewDialog(comparisons, self)
            if review.exec_() != QDialog.Accepted:
                return
            approved = review.approved
            approved.to_csv(os.path.join(self.temp_dir, "comparison-list.csv"), index=False)
            message = f"Metric analysis running for {len(approved)} comparison(s)..."
            print(message)
            QApplication.processEvents()

            metrics = calculate_metrics(approved)
            metrics.to_csv(os.path.join(self.temp_dir, "metrics.csv"), index=False)
            figure_dir = os.path.join(self.temp_dir, "figures")
            figure_count = 0
            for index, row in metrics.iterrows():
                if row["status"] != "ok":
                    continue
                try:
                    figure_path = plot_comparison(row, figure_dir, index + 1)
                    figure_count += 1
                    print(f"Saved comparison figure: {figure_path}")
                except Exception as exc:
                    warning = f"Figure for comparison {index + 1} failed: {exc}"
                    print(warning)
                QApplication.processEvents()
            print(f"Generated {figure_count} figure(s) in {figure_dir}")
            failures = metrics[metrics['status'] != 'ok']
            completed = len(metrics) - len(failures)
            message = (
                f"Metric analysis complete: {completed} succeeded, "
                f"{len(failures)} incomplete. Results saved to "
                f"{os.path.join(self.temp_dir, 'metrics.csv')}"
            )
            print(message)
            response = QMessageBox.question(
                self,
                "Metric analysis complete",
                message + "\n\nWould you like to clear the workflow and start again?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if response == QMessageBox.Yes:
                self.reset_workflow()

    def reset_workflow(self):
        """Clear the current selection and restore the initial GUI state.

        Existing output files are retained; restarting does not delete results.
        """
        self.dicom_dir = ""
        self.temp_dir = ""
        self.dicom_log = pd.DataFrame(
            columns=['FileName', 'Path', 'Modality', 'StructureNames', 'selected']
        )
        for attribute in ('dicom_log_updated', 'dicom_log_updated_RS'):
            if hasattr(self, attribute):
                delattr(self, attribute)
        for button in (
            self.dicom_button, self.temp_button, self.parse_button,
            self.select_contours_button,
        ):
            button.setStyleSheet(self.button_style())
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.dicom_path_display.clear()
        self.temp_path_display.clear()
        self.metadata_display.clear()
        self.display_metadata()

    def create_subdirectories_and_convert(self):
        """Create subdirectories and perform DICOM to NIfTI conversion with selected contours"""
        
        self.dicom_log_updated_RS = self.dicom_log_updated[self.dicom_log_updated["Modality"] == 'RTSTRUCT']
        
        if self.temp_dir and hasattr(self, 'dicom_log_updated'):
            
            # Set progress bar range to the number of RS files
            self.progress_bar.setRange(0, len(self.dicom_log_updated_RS))
            self.progress_bar.setValue(0)  # Initialize the progress bar
            
            for idx, (rs_file, selected_contours) in enumerate(zip(self.dicom_log_updated_RS['FileName'], self.dicom_log_updated_RS['selected'])):
                rs_file_name_without_extension = rs_file.replace(".dcm", "")
                output_dir = os.path.join(self.temp_dir, rs_file_name_without_extension)

                # Create directory if it doesn't exist
                if not os.path.exists(output_dir):
                    os.makedirs(output_dir)

                # Get the full path to the RS file (RTSTRUCT file)
                dicom_file_path = os.path.join(self.dicom_dir, rs_file)
                print(f"Processing {dicom_file_path}")

                # Get the CT directory (path to DICOM directory containing CT images)
                ct_directory = self.dicom_dir  # Path to the DICOM directory containing the CT images
                print(f"CT Directory: {ct_directory}")
                
                # Get the list of selected contours (split into list)
                selected_contours_list = selected_contours.split(", ")
                print(f"Selected Contours: {selected_contours_list}")
                
                # Call dcmrtstruct2nii conversion function, passing the necessary parameters
                try:
                    print(f"Converting {rs_file} to NIfTI format with selected contours...")
                    dcmrtstruct2nii(dicom_file_path, ct_directory, output_dir, structures=selected_contours_list)
                except Exception as e:
                    print(f"Error during conversion for {rs_file}: {e}")
                
                # Update progress bar after processing each RS file
                self.progress_bar.setValue(idx + 1)  # Increment progress bar
            
        # Once conversion is complete, reset progress bar
        self.progress_bar.setValue(0)
        print("Conversion complete.")

    def append_console_line(self, line):
        """Show terminal output in the activity pane without reprinting it."""
        if line:
            self.metadata_display.append(line)

    def display_metadata(self):
        """Refresh the DICOM summary without erasing the activity history."""
        if not self.dicom_dir:
            text = "No DICOM files loaded yet."
        elif not self.temp_dir:
            text = "No temporary directory selected yet."
        else:
            text = "DICOM Log:\n" + str(self.dicom_log)
        self.metadata_summary.setPlainText(text)

    def green_button_style(self):
        """Visual indicator that a workflow step has completed."""
        return (
            "QPushButton { background-color: #23865c; }"
            "QPushButton:hover { background-color: #1a704b; }"
            "QPushButton:pressed { background-color: #125b3c; }"
        )

    def button_style(self):
        """Restore the shared blue action-button styling."""
        return ""



# Run the PyQt5 application
def main():
    app = QApplication(sys.argv)
    window = ContourComparisonApp()
    window.show()
    with mirror_console(window):
        sys.exit(app.exec_())

if __name__ == "__main__":
    main()
