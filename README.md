# SuperPod

SuperPod provides simple, useful tools for the global medical physics community. Each subproject has its own dependencies and detailed README.

| Tool | What it does | Run from the repository root |
| --- | --- | --- |
| [DICOM Inspect](dicom-inspect/README.md) | Inspects one `.dcm` file from each subdirectory and exports selected DICOM metadata to `dicom_metadata.csv`. | `python dicom-inspect/src/inspect-dicom.py` |
| [DICOM Quick Edit](dicom-quick-edit/README.md) | Displays and edits selected textual/numeric metadata in one `.dcm` file; saves beside the original. | `python dicom-quick-edit/src/dicom-quick-edit.py` |
| [DICOM Viewer](dicom-viewer/README.md) | Displays CT/MR image series in three planes, with optional RTSTRUCT contour overlays. | `python dicom-viewer/src/dicom_viewer.py` |

## Getting started

Use Python 3 and a working desktop display (on WSL, WSLg or an X server). Set up a **separate virtual environment for each tool**. For example, from the SuperPod directory:

```bash
python3 -m venv dicom-quick-edit/.venv
source dicom-quick-edit/.venv/bin/activate
python -m pip install -r dicom-quick-edit/requirements.txt
python dicom-quick-edit/src/dicom-quick-edit.py
```

Replace `dicom-quick-edit` with `dicom-inspect` or `dicom-viewer` to run another tool. Deactivate the current environment first with `deactivate`. Dependency lists for Inspect and Viewer are broad pinned environment snapshots; they may contain optional or platform-specific packages. See the individual READMEs for each application's workflow and platform-specific build instructions.


- **Inspect** exports fields including patient name, patient ID, birth date, accession number, referring physician, and identifiers. 
- **Quick Edit** changes only selected fields; it does **not** anonymize files or remove private/nested tags, pixel annotations, or identifiers in related objects. Back up originals and validate edited files before use.
- **Viewer** loads local images and RTSTRUCT contours for inspection; it is not a diagnostic viewer or a clinically validated treatment-planning tool. Do not rely on its overlays for clinical decisions without independent validation.

These tools are provided for technical/educational use, not for clinical decision-making. DICOM handling and data protection remain the user's responsibility.
