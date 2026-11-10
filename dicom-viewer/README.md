# Light DICOM Viewer

Fast desktop app for viewing DICOM image series with optional DICOM RTSTRUCT contour overlays.

The app uses the same lightweight desktop stack as the related NIfTI/DICOM tools:

- `PyQt5` for the desktop interface
- `pyqtgraph` for fast 2D image display, zoom, and pan
- `pydicom` for DICOM image loading
- `rt-utils` for RTSTRUCT ROI mask extraction
- `numpy` for volume and contour overlay operations

## Python Scripts

There is one main Python script in `src/`.

### `dicom_viewer.py`

This is the main application.

Run this script for normal use:

```bash
python src/dicom_viewer.py
```

## Install

From the SuperPod repository root on Linux or WSL, create a local environment:

```bash
python3 -m venv dicom-viewer/.venv
source dicom-viewer/.venv/bin/activate
python -m pip install -r dicom-viewer/requirements.txt
```

A working GUI display is required. The pinned requirements include optional/platform-specific packages from a broader environment; if installation fails on your platform, review the dependencies before changing them.

## Run

From the SuperPod repository root, with the virtual environment activated:

```bash
python dicom-viewer/src/dicom_viewer.py
```

## Basic Workflow

1. Click **Load DICOM Image Directory**.
2. Select a folder containing the CT or MR DICOM image series.
   - CT and MR image series are supported when pixel data can be read by `pydicom`.
   - Files are sorted by image position when possible, then by slice metadata fallbacks.
   - A progress bar reports the fast header scan and pixel decoding phases.
3. The app automatically discovers RTSTRUCT files while scanning the folder.
   - If one RTSTRUCT is found, it is loaded automatically.
   - If multiple RTSTRUCT files are found, the app prompts you to select one.
   - If none are found, the image volume still loads normally.
4. Use the axial, sagittal, and coronal panes to inspect the volume.
5. Use the RTSTRUCT contour list to toggle individual ROIs on/off.
6. Use **Show contours** to globally show/hide all overlays.
7. Use **All** or **None** to quickly enable/disable every ROI.
8. Use the lower-right **Contour RTSTRUCT** pane to manage contour visibility while keeping image controls separate.
9. Use **Reset Zoom / Pan** to restore all 2D pane views.
10. Use **Center All Slices** to jump all slice sliders back to the middle of the volume.

## Viewer Layout

The UI is designed as a compact 4-pane layout:

```text
Controls                  Image panes
---------------------     -----------------------------
Input                     | Axial      | Sagittal      |
Window / Level            |------------|---------------|
View / logs               | Coronal    | Contour RTSTRUCT |
                          -----------------------------
```

The lower-right pane is dedicated to RTSTRUCT contour management. It contains the ROI visibility list plus quick **Show contours**, **All**, and **None** controls.

## Window / Level Controls

The viewer is designed for fast window/level changes:

- Presets:
  - CT Soft Tissue
  - CT Lung
  - CT Bone
  - CT Brain
  - MR / robust full range
  - Robust 1-99% from volume
- Numeric controls:
  - **Window width**
  - **Level center**
- Fast buttons:
  - **Wider**
  - **Narrower**
  - **Level +**
  - **Level -**

Window/level changes update the axial, sagittal, and coronal panes immediately.

## Zoom and Pan

Each 2D pyqtgraph pane supports standard interactive navigation:

- Mouse wheel: zoom
- Left-drag / middle-drag depending on platform settings: pan
- Right-click: pyqtgraph view menu
- **Reset Zoom / Pan**: reset all three 2D panes

## RTSTRUCT Contours

RTSTRUCT files are discovered during the initial DICOM header scan. The manual RTSTRUCT load button is intentionally not needed.

Contours are loaded through `rt-utils` and converted to boolean ROI masks aligned to the image volume. If an RTSTRUCT mask is returned as `y/x/z` with a one-slice difference from the displayed volume, the viewer crops/pads the mask to the loaded `z/y/x` volume instead of dropping the ROI.

For each visible ROI:

- Axial, sagittal, and coronal views show fast colored outline overlays.
- The ROI list controls whether that ROI is visible.
- The lower-right **Contour RTSTRUCT** pane keeps ROI toggles visible next to the image panes.

## Performance and Safety Notes

- DICOM files are read recursively from the selected image directory.
- CT/MR loading runs off the UI thread in a dedicated Qt worker.
- The initial scan uses a bounded thread pool with available CPU workers for fast DICOM header inspection without reading pixel data.
- Pixel arrays are decoded only after CT/MR image candidates have been identified, then decoded in parallel with a bounded worker pool.
- Threads are used instead of multiprocessing because DICOM header scanning and many pixel-decode workloads are largely file I/O, metadata parsing, and native-library work; this avoids process-spawn and large-object serialization overhead.
- Image loading only accepts DICOM objects with `Modality` equal to `CT` or `MR`.
- RTSTRUCT files are discovered during the header scan and then auto-loaded or selected from a prompt.
- RTSTRUCT loading runs in a dedicated Qt worker thread so contour rasterization does not block the UI.
- RTSTRUCT ROI loading updates the progress bar and status bar while contours are being parsed.
- RTSTRUCT, RTPLAN, RTDOSE, secondary captures, dose grids, and other non-CT/MR objects are not loaded as the image volume.
- Image pixels are converted with DICOM `RescaleSlope` and `RescaleIntercept` when present.
- The internal volume layout is `z/y/x`.
- RTSTRUCT masks from `rt-utils` are normalized into `z/y/x` before display.
- The app is optimized for responsive review and contour toggling, not editing or saving RTSTRUCT files.
- Contour alignment can be adjusted by cropping or padding when mask dimensions differ; this viewer is not clinically validated. Independently verify any findings before clinical use.
- DICOM files, screenshots, and logs may contain PHI. Never commit or share patient data in this repository.

## Build a Windows Executable

A Windows `.exe` should be built from Windows, not from Linux or WSL.

Create and activate a Windows virtual environment, then install the requirements before building.

From this project folder on Windows:

```bat
python -m venv .dicom-viewer.venv
.dicom-viewer.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Then run PyInstaller manually from the activated virtual environment:

```bat
python -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --name LightDicomViewer ^
  --distpath "dist" ^
  --workpath "build\pyinstaller-work" ^
  --specpath "build\pyinstaller-spec" ^
  "src\dicom_viewer.py"
```

The executable build will be placed here:

```text
<repo>\dicom-viewer\dist\LightDicomViewer\LightDicomViewer.exe
```

The app is built from:

```text
src\dicom_viewer.py
```
