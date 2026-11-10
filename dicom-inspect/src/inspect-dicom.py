# Author: Tucker Netherton, PhD,  with assistance GPT-6-sol, all code proof read and modified
import sys
import os
import pydicom
import pandas as pd
from PyQt5.QtWidgets import QApplication, QWidget, QPushButton, QVBoxLayout, QFileDialog, QProgressBar, QTextEdit, QMessageBox, QLabel
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor


class DicomInspectorApp(QWidget):
    def __init__(self):
        """Initialize the DICOM inspector interface and metadata table."""
        super().__init__()

        # Initialize the GUI components
        self.setWindowTitle("DICOM Inspector Tool")
        self.setGeometry(100, 100, 800, 600)
        self.setStyleSheet("background-color: #f2f2f2;")  # Set background color

        # Directory for DICOM files
        self.dicom_dir = ""
        self.save_dir = ""
        self.metadata = pd.DataFrame(columns=['PatientID', 'PatientName', 'StudyDescription', 'StudyDate'])

        # Create GUI layout
        self.layout = QVBoxLayout()

        # Title Label
        self.title_label = QLabel("DICOM Metadata Inspector", self)
        self.title_label.setFont(QFont("Arial", 16, QFont.Bold))
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet("color: #4CAF50; margin-bottom: 20px;")
        self.layout.addWidget(self.title_label)

        # Buttons
        self.load_button = QPushButton("Select DICOM Directory", self)
        self.load_button.clicked.connect(self.load_dicom_files)
        self.load_button.setStyleSheet(self.button_style())
        self.layout.addWidget(self.load_button)

        self.save_button = QPushButton("Select Save Directory", self)
        self.save_button.clicked.connect(self.select_save_directory)
        self.save_button.setStyleSheet(self.button_style())
        self.layout.addWidget(self.save_button)

        self.inspect_button = QPushButton("Inspect DICOM Directory", self)
        self.inspect_button.clicked.connect(self.inspect_dicom_directory)
        self.inspect_button.setStyleSheet(self.button_style())
        self.layout.addWidget(self.inspect_button)

        # Display Metadata Window
        self.metadata_display = QTextEdit(self)
        self.metadata_display.setReadOnly(True)
        self.metadata_display.setStyleSheet("background-color: white; font-size: 14px; padding: 10px; border-radius: 5px; border: 1px solid #ccc;")
        self.layout.addWidget(self.metadata_display)

        # Progress Bar
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setStyleSheet("QProgressBar {background-color: #e0e0e0; border-radius: 10px; height: 20px;} "
                                        "QProgressBar::chunk {background-color: #4CAF50; border-radius: 10px;}") 
        self.layout.addWidget(self.progress_bar)

        # Set layout with some padding and margins
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(20)

        # Set the window's main layout
        self.setLayout(self.layout)

    def button_style(self):
        """Returns the style for buttons"""
        return (
            "QPushButton {"
            "background-color: #2196F3; color: white; padding: 10px; border-radius: 5px; font-size: 16px;"
            "border: none; margin-bottom: 10px;}"
            "QPushButton:hover {background-color: #1976D2;} "
            "QPushButton:pressed {background-color: #1565C0;}"
        )

    def load_dicom_files(self):
        """Open a dialog to select DICOM files and load metadata"""
        self.dicom_dir = QFileDialog.getExistingDirectory(self, "Select DICOM Directory")
        if self.dicom_dir:
            self.load_button.setStyleSheet(self.green_button_style())  # Change button to green after selection
            self.metadata_display.append("Dicom directory: " +str(self.dicom_dir))

    def select_save_directory(self):
        """Open a dialog to select the save directory"""
        self.save_dir = QFileDialog.getExistingDirectory(self, "Select Save Directory")
        if self.save_dir:
            self.save_button.setStyleSheet(self.green_button_style())  # Change button to green after selection
            self.metadata_display.append("Save directory: " +str(self.save_dir))

    def green_button_style(self):
        """Returns the green button style"""
        return (
            "QPushButton {"
            "background-color: #4CAF50; color: white; padding: 10px; border-radius: 5px; font-size: 16px;"
            "border: none; margin-bottom: 10px;} "
            "QPushButton:hover {background-color: #388E3C;} "
            "QPushButton:pressed {background-color: #2C6B2F;}"
        )

    def inspect_dicom_directory(self):
        """Inspect the DICOM directory and save the metadata to a DataFrame"""
        if not self.dicom_dir or not self.save_dir:
            QMessageBox.warning(self, "Warning", "Please select both DICOM and Save directories before inspecting.")
            return

        dicom_files = []
        for root, dirs, files in os.walk(self.dicom_dir):
            for dir_name in dirs:
                # Only inspect the first DICOM file in each subdir
                subdir_path = os.path.join(root, dir_name)
                dicom_files_in_subdir = [os.path.join(subdir_path, file) for file in os.listdir(subdir_path) if file.lower().endswith(".dcm")]
                if dicom_files_in_subdir:
                    dicom_files.append(dicom_files_in_subdir[0])

        total_files = len(dicom_files)

        if total_files == 0:
            QMessageBox.warning(self, "Warning", "No DICOM files found in the selected directory.")
            return
        else:
            self.metadata_display.append("Detected directories: " +str(total_files))

        # Set up progress bar
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(total_files)

        # Process the DICOM files sequentially
        for idx, dicom_path in enumerate(dicom_files):
            try:
                dicom_data = pydicom.dcmread(dicom_path, force=True)

                # Log metadata
                self.log_metadata(dicom_data)

                # Update progress bar
                self.progress_bar.setValue(idx + 1)
            except Exception as e:
                self.metadata_display.append(f"Error reading {dicom_path}: {str(e)}")

        # Save the metadata DataFrame
        self.save_metadata()

        # Display summary and reset state
        self.metadata_display.append("\nInspection completed.")
        self.progress_bar.setValue(0)

    def log_metadata(self, dicom_data):
        """Log important metadata from DICOM"""
        tag_list = [
                "PatientID", "PatientName", "StudyDescription", "StudyInstanceUID", "AcquisitionTime", "StudyDate",
                "Modality", "SliceLocation", "SOPInstanceUID", "PixelSpacing", "ImagePositionPatient",
                "StudyTime", "SpecificCharacterSet", "ImageType", "InstanceCreationDate", "InstanceCreationTime",
                "SOPClassUID", "AcquisitionDate", "ContentDate", "ContentTime", "AccessionNumber", "ConversionType",
                "Manufacturer", "ReferringPhysicianName", "StationName", "OperatorsName", "ManufacturerModelName",
                "IrradiationEventUID", "PatientBirthDate", "PatientBirthTime", "PatientSex", "DeviceSerialNumber",
                "SoftwareVersions", "PatientPosition", "SeriesInstanceUID", "StudyID", "SeriesNumber",
                "AcquisitionNumber", "InstanceNumber", "PatientOrientation", "FrameOfReferenceUID",
                "PositionReferenceIndicator", "SamplesPerPixel", "PhotometricInterpretation", "PlanarConfiguration",
                "Rows", "Columns", "BitsAllocated", "BitsStored", "HighBit", "PixelRepresentation",
                "PixelIntensityRelationship", "PixelIntensityRelationshipSign", "WindowCenter", "WindowWidth",
                "RescaleIntercept", "RescaleSlope", "RescaleType", "RTImageLabel", "RTImageDescription",
                "ReportedValuesOrigin", "RTImagePlane", "XRayImageReceptorTranslation", "XRayImageReceptorAngle",
                "RTImageOrientation", "ImagePlanePixelSpacing", "RTImagePosition", "RadiationMachineName",
                "RadiationMachineSAD", "RTImageSID", "FractionNumber", "ExposureSequence", "PrimaryDosimeterUnit",
                "GantryAngle", "BeamLimitingDeviceAngle", "PatientSupportAngle", "TableTopVerticalPosition",
                "TableTopLongitudinalPosition", "TableTopLateralPosition", "IsocenterPosition",
                "ReferencedRTPlanSequence", "ReferencedBeamNumber", "StartCumulativeMetersetWeight",
                "EndCumulativeMetersetWeight", "ReferencedFractionGroupNumber", "PrivateCreator", "XMLStream",
                "DataLengthXMLStream", "ExtendedInterfaceFormatTag", "PrivateTagData"
            ]

        metadata_dict = {tag: dicom_data.get(tag, 'Unknown') for tag in tag_list}
        metadata_df = pd.DataFrame([metadata_dict])
        self.metadata = pd.concat([self.metadata, metadata_df], ignore_index=True)


    def save_metadata(self):
        """Save the metadata to the selected directory"""
        if self.save_dir:
            save_path = os.path.join(self.save_dir, "dicom_metadata.csv")
            self.metadata.to_csv(save_path, index=False)
            self.metadata_display.append(f"Metadata saved to {save_path}")

    def green_button_style(self):
        """Returns the green button style"""
        return (
            "QPushButton {"
            "background-color: #4CAF50; color: white; padding: 10px; border-radius: 5px; font-size: 16px;"
            "border: none; margin-bottom: 10px;} "
            "QPushButton:hover {background-color: #388E3C;} "
            "QPushButton:pressed {background-color: #2C6B2F;}"
        )


def main():
    """Start the DICOM inspector desktop application."""
    app = QApplication(sys.argv)
    window = DicomInspectorApp()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
