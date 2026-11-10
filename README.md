# SuperPod

SuperPod provides simple, useful tools for the global medical physics community. Each subproject has its own dependencies and detailed README.

| Tool | What it does | Run from the repository root |
| --- | --- | --- |
| [DICOM Inspect](dicom-inspect/README.md) | Inspects one `.dcm` file from each subdirectory and exports selected DICOM metadata to `dicom_metadata.csv`. | `python dicom-inspect/src/inspect-dicom.py` |
| [DICOM Quick Edit](dicom-quick-edit/README.md) | Displays and edits selected textual/numeric metadata in one `.dcm` file; saves beside the original. | `python dicom-quick-edit/src/dicom-quick-edit.py` |
| [DICOM Viewer](dicom-viewer/README.md) | Displays CT/MR image series in three planes, with optional RTSTRUCT contour overlays. | `python dicom-viewer/src/dicom_viewer.py` |

Read more about our work to increase global access to high quality radiotherapy treatment planning:

- Olanrewaju A, Court LE, Zhang L, Naidoo K, Burger H, Dalvie S, Wetter J, Parkes J, Trauernicht CJ, McCarroll RE, Cardenas C, Peterson CB, Benson KRK, du Toit M, van Reenen R, Beadle BM. Clinical Acceptability of Automated Radiation Treatment Planning for Head and Neck Cancer Using the Radiation Planning Assistant. Pract Radiat Oncol. 2021 May-Jun;11(3):177-184. doi: 10.1016/j.prro.2020.12.003. Epub 2021 Feb 25. PMID: 33640315; PMCID: PMC9272530.

- Court LE. The Radiation Planning Assistant: addressing the global gap in radiotherapy services
The Lancet Oncology, 25, 277-278

- Netherton TJ. et al. Artificial Intelligence–Powered Radiotherapy for Resource-Limited Settings: Advancing Cervical and Prostate Cancer Treatment Planning With the Radiation Planning Assistant. JCO Glob Oncol 12, e2500702(2026).
DOI:10.1200/GO-25-00702

## Getting started (for non-programmers)

Check the releases on the right side of the page, download windows programs to use!

## Getting started (for programmers/datascientists)

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


