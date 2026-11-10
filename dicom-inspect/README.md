# DICOM Inspector Tool

This application provides a graphical interface for inspecting DICOM directories and extracting metadata from DICOM files. It is designed to help users quickly review and export key metadata from medical imaging datasets.

## Features

- Select DICOM and save directories via GUI
- Inspects the first DICOM file in each subdirectory
- Extracts a comprehensive set of DICOM metadata fields
- Saves metadata as a CSV file for further analysis
- Progress bar and status display

## Installation

1. Create and activate a virtual environment (recommended).
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
   Ensure `pydicom`, `PyQt5`, and `pandas` are installed.

## Usage

1. Run the application:
   ```
   python src/inspect-dicom.py
   ```
2. In the GUI:
   - **Select DICOM Directory**: Choose the folder containing your DICOM files (the tool inspects the first file in each subdirectory).
   - **Select Save Directory**: Choose a folder where the metadata CSV will be saved.
   - **Inspect DICOM Directory**: Extracts metadata and saves it as dicom_metadata.csv in the save directory.
   - Progress is shown in the progress bar, and status messages are displayed in the metadata window.

## Button Descriptions

- **Select DICOM Directory**: Opens a folder dialog to select the source DICOM files.
- **Select Save Directory**: Opens a folder dialog to select where the metadata CSV will be saved.
- **Inspect DICOM Directory**: Runs the inspection and metadata extraction process.
- **Progress Bar**: Indicates progress during inspection.
- **Metadata Display**: Shows status messages and summary.

## Recommended Screenshots

- Main application window (showing all buttons and metadata display)

Including a screenshot in the README will help users understand the workflow and interface.

## Notes

- Only the first DICOM file in each subdirectory is inspected.
- Extracted metadata is saved as dicom_metadata.csv in the selected save directory.
- Useful for quickly reviewing and exporting DICOM metadata for large datasets.
