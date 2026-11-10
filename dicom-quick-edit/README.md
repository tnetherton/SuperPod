# DICOM Quick Edit

A desktop editor for changing selected values in **one `.dcm` file at a time**. This tool does **not** de-identify a file or scrub private, nested, or image-embedded information.

## Features

- Browse for a `.dcm` file or drag and drop one into the window.
- Browse and filter metadata by tag, name, VR, or value, including nested sequence fields.
- Select an editable textual or numeric field, enter a replacement, and click **Apply field change**. Apply multiple changes before saving.
- **Save (replace original)** writes to the original filename after confirmation; **Save as new file (same folder)** writes a new file beside the source.
- Binary fields, sequences themselves, and the DICOM file-meta header are read-only. Unchanged elements, including pixel data, remain in the file. SOP Class/Instance UID changes also update the corresponding file-meta entries.
- Unsaved applied changes prompt before opening another file or closing. Files without a valid DICOM header are rejected rather than forced open.

## Set up and run

From the SuperPod repository root on Linux or WSL:

```bash
python3 -m venv dicom-quick-edit/.venv
source dicom-quick-edit/.venv/bin/activate
python -m pip install -r dicom-quick-edit/requirements.txt
python dicom-quick-edit/src/dicom-quick-edit.py
```

A working GUI display is required (WSLg or an X server if using WSL). Use only data you are authorized to access; do not publish patient files or edited outputs.

## Editing notes

1. Select or drop a `.dcm` file. Select a metadata row; expand sequences to reach nested rows.
2. Edit the value below the tree. Use a backslash (`\`) between values in a multi-valued field. Press Enter or click **Apply field change**. Typing without applying does not change the loaded dataset.
3. Choose **Save (replace original)** or **Save as new file (same folder)**. Confirm before replacing an existing file. The new-file option defaults to `originalname_edited.dcm`.

Text/numeric DICOM VRs are editable; binary data, pixel data, unknown VRs, and sequence containers are read-only. Numeric fields reject invalid numbers. Review edited values and test saved files with downstream DICOM software. Changing identifiers can break references between files: this tool does not update related DICOM objects. Back up valuable originals before replacing them.

## Optional Windows executable

PyInstaller is not a cross-compiler. Build on Windows with Windows Python to make a Windows `.exe`; building on Linux/WSL creates a Linux executable instead.

From the `dicom-quick-edit` folder in Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m PyInstaller --noconfirm --clean --onefile --windowed --name dicom-quick-edit src\dicom-quick-edit.py
```

The Windows build appears in `dist\dicom-quick-edit.exe`. The virtual environment and generated build files are ignored by the repository's `.gitignore`. If PowerShell blocks activation, use `.\.venv\Scripts\python.exe` in place of `python` for the installation and build commands. Test the executable on Windows before distribution.