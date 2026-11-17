# Quantitative Contour Comparison Tool

A PyQt5 desktop tool for selecting RTSTRUCT contours, converting them to NIfTI with `dcmrtstruct2nii`, reviewing contour pairs, and calculating Dice similarity coefficient (DSC) and mean surface distance (MSD).

## Installation

From this directory, create a Python virtual environment and install the dependencies:

```bash
uv venv .venv-contour-compare
source .venv-contour-compare/bin/activate
uv pip install -r requirements.txt
python src/contour-compare.py
```

A desktop with Qt support is required for the GUI. To run the workflow tests:

```bash
.venv-contour-compare/bin/python -m unittest discover -s tests -v
```

## Workflow

1. Select the DICOM directory (CT slices and RTSTRUCT files in the same directory) and a temporary output directory.
2. Click **Parse DICOM Files**. The app reads `.dcm` files in the selected directory and saves `dicom_log.csv` in the temporary directory.
3. Click **Select Contours**, select ROIs under their RTSTRUCT files, and confirm. `dicom_log_updated.csv` then contains **only** the selected RTSTRUCT files and the complete CT series referenced by their selected contours. It records absolute DICOM paths in `Path`; RTSTRUCT `StructureNames` and `selected` contain only selected ROIs. If references cannot uniquely identify a CT series, the app stops and shows a warning.
4. The existing conversion call writes each RTSTRUCT's selected masks under its filename-stem subdirectory in the temporary directory. The conversion function and its CT-directory argument are unchanged; filtering the CSV does not constrain which series the third-party converter chooses when the source directory has multiple CT series.
5. Review all unordered pairs of selected contours in the popup. A selection is identified by its RTSTRUCT *and* contour name, so the same name from two RTSTRUCTs produces two distinct selections. Uncheck pairs you do not want to run and choose contour 1 or contour 2 as ground truth for each pair. Confirm to save the approved rows to `comparison-list.csv`, calculate metrics, and generate figures; cancel prevents these steps.
6. `metrics.csv` has the same columns as `comparison-list.csv` plus `dsc`, `msd`, `dsc-gt-voi`, `msd-gt-voi`, and `status`. The pair's `path_1` and `path_2` are absolute **NIfTI mask paths**; `structure_file_1` and `structure_file_2` identify the source RTSTRUCT filenames. Conversion failures and missing masks are recorded in `status` with missing metrics instead of pretending those pairs succeeded.
7. Figures are generated automatically for successful comparisons: three-plane axial, coronal, and sagittal CT overlays go into the temporary directory's `figures/` subdirectory. Ground-truth contours are solid blue; the other contour is dashed red. The plot uses the converted `image.nii.gz` and a crop centered on the union of the two masks, following the approach in `plot_MIST_figures.py`. Figure failures are reported in the application log; they do not discard the CSV metrics. When analysis finishes, a popup offers to clear the UI and start again without deleting saved outputs.

For metrics, masks are compared on the ground truth's physical grid (nearest-neighbor resampling if needed), cropped to the union of both nonempty masks' 3D bounding boxes, and passed to SimpleITK overlap and surface-distance operations. `dsc` and `msd` use the full aligned masks. `dsc-gt-voi` and `msd-gt-voi` restrict **both** masks to the tight 3D bounding box of the selected ground-truth contour: prediction outside that box is ignored; a zero-valued border added *after* cropping keeps surface distances well-defined at the box edge. DSC is unitless; symmetric MSD is in millimeters. When only one full mask is empty, full DSC is 0 and MSD is undefined. If the ground truth is empty, both VOI metrics are undefined; if the prediction is empty inside its box, VOI DSC is 0 and VOI MSD is undefined. Such rows are marked in `status`.

Python console output produced while the GUI runs (including conversion and analysis messages and Python warnings) is mirrored to the activity pane while remaining visible in the terminal. The DICOM summary is shown separately so refreshing it does not erase activity history. Choosing to reset the workflow clears the activity pane.

**Note:** The existing conversion loop catches and prints conversion errors, then proceeds. If the converter selects an incompatible CT series, the dimension-mismatch error can still occur; the metrics CSV will identify missing converted masks.

## Optional plotting script

`src/create_plots_gui.py` is a separate plotting utility for existing comparison results. It expects `results.csv` with `nf1` and `nf2` NIfTI-mask paths and `image.nii.gz` beside the first mask. It does **not** currently read the new `metrics.csv` directly.