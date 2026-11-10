# Author: Tucker Netherton, PhD,  with assistance GPT-6-sol, all code proof read and modified
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np


def configure_qt_plugin_paths() -> None:
    """Prefer PyQt5's Qt plugins over OpenCV's bundled Qt plugins.

    The regular opencv-python wheel can set Qt plugin paths to cv2/qt/plugins.
    When PyQt5 then starts a QApplication, Qt may find OpenCV's xcb plugin first
    and abort with: "Could not load the Qt platform plugin xcb ... cv2/qt/plugins".
    This app does not use OpenCV directly, so remove cv2 plugin paths before Qt imports.
    """
    for variable in ("QT_QPA_PLATFORM_PLUGIN_PATH", "QT_PLUGIN_PATH"):
        value = os.environ.get(variable)
        if value and "cv2" in value and "qt" in value.lower():
            os.environ.pop(variable, None)

    try:
        import PyQt5

        pyqt_plugin_root = os.path.join(os.path.dirname(PyQt5.__file__), "Qt5", "plugins")
        pyqt_platforms = os.path.join(pyqt_plugin_root, "platforms")

        if os.path.isdir(pyqt_plugin_root):
            os.environ["QT_PLUGIN_PATH"] = pyqt_plugin_root
        if os.path.isdir(pyqt_platforms):
            os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = pyqt_platforms
    except Exception:
        pass


configure_qt_plugin_paths()

import pydicom
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets
from rt_utils import RTStructBuilder


pg.setConfigOptions(imageAxisOrder="row-major", antialias=True)


@dataclass
class DicomSlice:
    path: str
    dataset: pydicom.dataset.Dataset
    sort_value: float


@dataclass
class DecodedSlice:
    path: str
    dataset: pydicom.dataset.Dataset
    sort_value: float
    pixel_array: np.ndarray


@dataclass
class VolumeData:
    directory: str
    files: List[str]
    datasets: List[pydicom.dataset.Dataset]
    volume: np.ndarray
    modality: str
    description: str
    spacing_zyx: Tuple[float, float, float]
    rtstruct_paths: List[str] = field(default_factory=list)
    patient_position: str = ""
    study_description: str = ""
    series_description: str = ""
    series_instance_uid: str = ""


@dataclass
class RoiRecord:
    name: str
    mask: np.ndarray
    color: Tuple[int, int, int]
    enabled: bool = True


@dataclass
class ViewerState:
    volume_data: Optional[VolumeData] = None
    rois: Dict[str, RoiRecord] = field(default_factory=dict)


def is_image_dataset(dataset: pydicom.dataset.Dataset) -> bool:
    """Return True only for CT/MR image slices with pixel data.

    This intentionally rejects RTSTRUCT, RTPLAN, RTDOSE, secondary captures,
    dose grids, and other DICOM objects that may live in the same folder.
    """
    modality = str(getattr(dataset, "Modality", "")).upper()
    return (
        modality in {"CT", "MR"}
        and hasattr(dataset, "PixelData")
        and hasattr(dataset, "Rows")
        and hasattr(dataset, "Columns")
    )


def dicom_sort_value(dataset: pydicom.dataset.Dataset) -> float:
    """Sort slices by image position along the slice normal when possible."""
    try:
        orientation = np.asarray(dataset.ImageOrientationPatient, dtype=float)
        position = np.asarray(dataset.ImagePositionPatient, dtype=float)
        row_cosines = orientation[:3]
        col_cosines = orientation[3:]
        normal = np.cross(row_cosines, col_cosines)
        return float(np.dot(position, normal))
    except Exception:
        pass

    for attribute in ("SliceLocation", "InstanceNumber"):
        try:
            return float(getattr(dataset, attribute))
        except Exception:
            continue

    return 0.0


def estimate_slice_spacing(sorted_datasets: Sequence[pydicom.dataset.Dataset], sort_values: Sequence[float]) -> float:
    """Estimate slice spacing from DICOM metadata with robust fallbacks."""
    if len(sort_values) > 1:
        diffs = np.diff(np.asarray(sort_values, dtype=float))
        diffs = np.abs(diffs[np.isfinite(diffs)])
        diffs = diffs[diffs > 1.0e-6]
        if diffs.size:
            return float(np.median(diffs))

    for dataset in sorted_datasets:
        for attribute in ("SpacingBetweenSlices", "SliceThickness"):
            try:
                value = float(getattr(dataset, attribute))
                if value > 0:
                    return value
            except Exception:
                continue

    return 1.0


def default_window_level(volume: np.ndarray) -> Tuple[float, float]:
    """Compute a useful default window/level from robust percentiles."""
    finite = volume[np.isfinite(volume)]
    if finite.size == 0:
        return 1.0, 0.0

    low, high = np.percentile(finite, (1, 99))
    if high <= low:
        low = float(np.min(finite))
        high = float(np.max(finite))

    if high <= low:
        return 1.0, float(low)

    width = float(high - low)
    level = float((high + low) / 2.0)
    return width, level


def reconcile_mask_shape(mask_zyx: np.ndarray, volume_shape: Tuple[int, int, int]) -> np.ndarray:
    """Crop or pad a boolean z/y/x mask to the loaded image volume shape.

    RTSTRUCT converters sometimes return one extra or one fewer slice than the
    selected image stack because a folder contains localizer/derived slices, a
    failed pixel decode removed one CT/MR instance, or metadata references a
    slightly different export.  For display, a simple edge crop/pad is safer
    than dropping the whole ROI.  The operation preserves the origin side of the
    mask and only adjusts dimensions that differ from the displayed volume.
    """
    mask_zyx = np.asarray(mask_zyx, dtype=bool)
    fixed = np.zeros(volume_shape, dtype=bool)

    source_slices = tuple(slice(0, min(mask_zyx.shape[axis], volume_shape[axis])) for axis in range(3))
    target_slices = tuple(slice(0, min(mask_zyx.shape[axis], volume_shape[axis])) for axis in range(3))
    fixed[target_slices] = mask_zyx[source_slices]
    return fixed


def normalize_mask_from_rt_utils(mask: np.ndarray, volume_shape: Tuple[int, int, int]) -> np.ndarray:
    """Convert rt-utils masks into internal z/y/x layout with tolerant sizing.

    Internal images are stored as ``z/y/x``.  ``rt-utils`` commonly returns
    masks as ``rows/columns/slices`` (``y/x/z``), but some toolchains emit
    ``x/y/z`` or already-normalized ``z/y/x`` arrays.  This function detects
    those layouts by matching the two in-plane dimensions first, then reconciles
    minor slice-count mismatches by cropping/padding instead of rejecting the
    ROI.
    """
    mask = np.asarray(mask).astype(bool)

    if mask.ndim != 3:
        raise ValueError(f"RTSTRUCT mask shape {mask.shape} is not 3D.")

    candidates: List[np.ndarray] = [mask]

    # rt-utils common layout: rows/columns/slices == y/x/z.
    if mask.shape[0] == volume_shape[1] and mask.shape[1] == volume_shape[2]:
        candidates.append(np.transpose(mask, (2, 0, 1)))

    # Alternate x/y/z layout.
    if mask.shape[0] == volume_shape[2] and mask.shape[1] == volume_shape[1]:
        candidates.append(np.transpose(mask, (2, 1, 0)))

    # If the exact z/y/x shape is present, prefer it immediately.
    for candidate in candidates:
        if candidate.shape == volume_shape:
            return candidate

    # Otherwise choose the candidate with best in-plane agreement and smallest
    # total shape difference, then crop/pad to match the displayed volume.
    def score(candidate: np.ndarray) -> Tuple[int, int]:
        """Rank a mask layout by in-plane agreement and total shape difference."""
        in_plane_mismatch = int(candidate.shape[1] != volume_shape[1]) + int(candidate.shape[2] != volume_shape[2])
        total_delta = sum(abs(candidate.shape[axis] - volume_shape[axis]) for axis in range(3))
        return in_plane_mismatch, total_delta

    best = min(candidates, key=score)
    if score(best)[0] > 0:
        raise ValueError(f"RTSTRUCT mask shape {mask.shape} cannot be aligned to image volume shape {volume_shape}.")

    return reconcile_mask_shape(best, volume_shape)


def contour_rgba(mask_2d: np.ndarray, color: Tuple[int, int, int], alpha: int = 210) -> np.ndarray:
    """Create an RGBA outline overlay from a 2D boolean mask."""
    mask = np.asarray(mask_2d, dtype=bool)
    rgba = np.zeros(mask.shape + (4,), dtype=np.ubyte)
    if not mask.any():
        return rgba

    eroded = mask.copy()
    eroded[1:-1, 1:-1] = (
        mask[1:-1, 1:-1]
        & mask[:-2, 1:-1]
        & mask[2:, 1:-1]
        & mask[1:-1, :-2]
        & mask[1:-1, 2:]
    )
    boundary = mask & ~eroded
    if not boundary.any():
        boundary = mask

    rgba[boundary, 0] = color[0]
    rgba[boundary, 1] = color[1]
    rgba[boundary, 2] = color[2]
    rgba[boundary, 3] = alpha
    return rgba


def blend_overlays(base_shape: Tuple[int, int], overlays: Sequence[Tuple[np.ndarray, Tuple[int, int, int]]]) -> np.ndarray:
    """Blend multiple ROI outline overlays into one RGBA image for one plane."""
    rgba = np.zeros(base_shape + (4,), dtype=np.ubyte)
    for mask, color in overlays:
        current = contour_rgba(mask, color)
        active = current[..., 3] > 0
        rgba[active] = current[active]
    return rgba


class DicomLoadWorker(QtCore.QObject):
    """Background DICOM scanner/loader optimized for mixed radiotherapy folders.

    The worker performs a fast parallel metadata pass first.  That pass avoids
    pixel data reads, identifies CT/MR image files, discovers RTSTRUCT objects,
    and ignores RTDOSE/RTPLAN/other DICOM objects.  Pixel arrays are decoded only
    for the selected CT/MR image stack, keeping startup responsive even when a
    treatment-planning folder contains many non-image DICOM files.
    """

    log = QtCore.Signal(str)
    progress = QtCore.Signal(int, int, str)
    finished = QtCore.Signal(bool, object, str)

    def __init__(self, dicom_directory: str):
        """Initialize the background scanner for a selected DICOM directory."""
        super().__init__()
        self.dicom_directory = dicom_directory
        self._cancel_requested = False

    @staticmethod
    def _scan_one(path: str) -> Optional[Tuple[str, str, str, float, pydicom.dataset.Dataset]]:
        """Read lightweight DICOM metadata for one path.

        Returns ``(kind, modality, series_uid, sort_value, dataset)`` where kind
        is ``image``, ``rtstruct``, or ``other``.  Pixel data is intentionally
        skipped in this pass for speed and low memory pressure.
        """
        try:
            dataset = pydicom.dcmread(path, force=True, stop_before_pixels=True)
        except Exception:
            return None

        modality = str(getattr(dataset, "Modality", "")).upper()
        series_uid = str(getattr(dataset, "SeriesInstanceUID", ""))

        if modality == "RTSTRUCT":
            return "rtstruct", modality, series_uid, 0.0, dataset

        if modality in {"CT", "MR"} and hasattr(dataset, "Rows") and hasattr(dataset, "Columns"):
            return "image", modality, series_uid, dicom_sort_value(dataset), dataset

        return "other", modality or "UNKNOWN", series_uid, 0.0, dataset

    @staticmethod
    def _decode_one(item: DicomSlice) -> Optional[DecodedSlice]:
        """Fully read and decode one CT/MR slice for parallel pixel loading."""
        dataset = pydicom.dcmread(item.path, force=True)
        if not is_image_dataset(dataset):
            return None

        pixel_array = dataset.pixel_array.astype(np.float32)
        slope = float(getattr(dataset, "RescaleSlope", 1.0))
        intercept = float(getattr(dataset, "RescaleIntercept", 0.0))
        pixel_array = pixel_array * slope + intercept

        return DecodedSlice(
            path=item.path,
            dataset=dataset,
            sort_value=item.sort_value,
            pixel_array=pixel_array,
        )

    def _all_candidate_files(self) -> List[str]:
        """Return sorted regular files under the selected directory."""
        paths: List[str] = []
        for root, _, filenames in os.walk(self.dicom_directory):
            for filename in sorted(filenames):
                path = os.path.join(root, filename)
                if os.path.isfile(path):
                    paths.append(path)
        return paths

    @QtCore.Slot()
    def run(self) -> None:
        """Scan DICOM headers and decode CT/MR slices in background threads."""
        try:
            paths = self._all_candidate_files()
            if not paths:
                self.finished.emit(False, None, "The selected directory does not contain any files.")
                return

            max_workers = max(1, min(32, (os.cpu_count() or 1) + 4, len(paths)))
            self.log.emit(f"Scanning {len(paths)} file(s) with {max_workers} worker(s)...")
            self.progress.emit(0, len(paths), "Scanning DICOM headers")

            slices: List[DicomSlice] = []
            rtstruct_paths: List[str] = []

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_path = {executor.submit(self._scan_one, path): path for path in paths}

                for scanned_count, future in enumerate(as_completed(future_to_path), start=1):
                    if self._cancel_requested:
                        self.finished.emit(False, None, "DICOM load cancelled.")
                        return

                    path = future_to_path[future]
                    result = future.result()
                    if result is None:
                        self.progress.emit(scanned_count, len(paths), "Scanning DICOM headers")
                        continue

                    kind, modality, _, sort_value, dataset = result

                    if kind == "rtstruct":
                        rtstruct_paths.append(path)
                    elif kind == "image":
                        slices.append(DicomSlice(path=path, dataset=dataset, sort_value=sort_value))
                    elif hasattr(dataset, "PixelData") and modality not in {"CT", "MR"}:
                        self.log.emit(f"Skipped non-CT/MR DICOM object ({modality}): {os.path.basename(path)}")

                    if scanned_count == 1 or scanned_count % 25 == 0 or scanned_count == len(paths):
                        self.progress.emit(scanned_count, len(paths), "Scanning DICOM headers")

            rtstruct_paths.sort()
            if rtstruct_paths:
                self.log.emit(f"Discovered {len(rtstruct_paths)} RTSTRUCT file(s).")

            if not slices:
                self.finished.emit(False, None, "No CT or MR DICOM image slices were found.")
                return

            slices.sort(key=lambda item: item.sort_value)
            sorted_datasets = [item.dataset for item in slices]
            sort_values = [item.sort_value for item in slices]

            decoded_items: List[DecodedSlice] = []
            pixel_workers = max(1, min(16, (os.cpu_count() or 1), len(slices)))
            self.log.emit(f"Decoding {len(slices)} CT/MR slice(s) with {pixel_workers} worker(s)...")
            self.progress.emit(0, len(slices), "Decoding CT/MR pixels")

            with ThreadPoolExecutor(max_workers=pixel_workers) as executor:
                future_to_slice = {executor.submit(self._decode_one, item): item for item in slices}

                for decoded_count, future in enumerate(as_completed(future_to_slice), start=1):
                    if self._cancel_requested:
                        self.finished.emit(False, None, "DICOM load cancelled.")
                        return

                    item = future_to_slice[future]
                    try:
                        decoded = future.result()
                    except Exception as exc:
                        self.log.emit(f"Skipped image candidate after full read ({os.path.basename(item.path)}): {exc}")
                        decoded = None

                    if decoded is None:
                        self.log.emit(f"Skipped image candidate after full read: {os.path.basename(item.path)}")
                    else:
                        decoded_items.append(decoded)

                    if decoded_count == 1 or decoded_count % 10 == 0 or decoded_count == len(slices):
                        self.progress.emit(decoded_count, len(slices), "Decoding CT/MR pixels")
                        self.log.emit(f"Decoded {decoded_count} / {len(slices)} image slice candidate(s)...")

            if not decoded_items:
                self.finished.emit(False, None, "No CT or MR image slices could be decoded.")
                return

            decoded_items.sort(key=lambda item: item.sort_value)
            arrays = [item.pixel_array for item in decoded_items]
            sorted_datasets = [item.dataset for item in decoded_items]
            sort_values = [item.sort_value for item in decoded_items]
            volume = np.stack(arrays, axis=0).astype(np.float32, copy=False)

            first = sorted_datasets[0]
            try:
                pixel_spacing = tuple(float(value) for value in first.PixelSpacing)
                row_spacing = pixel_spacing[0]
                col_spacing = pixel_spacing[1]
            except Exception:
                row_spacing = 1.0
                col_spacing = 1.0

            slice_spacing = estimate_slice_spacing(sorted_datasets, sort_values)
            modality = str(getattr(first, "Modality", "DICOM")).upper()
            if modality not in {"CT", "MR"}:
                self.finished.emit(False, None, f"Unsupported image modality: {modality}. Only CT and MR are supported.")
                return

            series_description = str(getattr(first, "SeriesDescription", ""))
            study_description = str(getattr(first, "StudyDescription", ""))
            patient_position = str(getattr(first, "PatientPosition", ""))
            series_instance_uid = str(getattr(first, "SeriesInstanceUID", ""))

            description_parts = [modality]
            if study_description:
                description_parts.append(study_description)
            if series_description:
                description_parts.append(series_description)

            volume_data = VolumeData(
                directory=self.dicom_directory,
                files=[item.path for item in decoded_items],
                datasets=sorted_datasets,
                volume=volume,
                modality=modality,
                description=" | ".join(description_parts),
                spacing_zyx=(slice_spacing, row_spacing, col_spacing),
                rtstruct_paths=rtstruct_paths,
                patient_position=patient_position,
                study_description=study_description,
                series_description=series_description,
                series_instance_uid=series_instance_uid,
            )
            self.finished.emit(True, volume_data, "")
        except Exception as exc:
            self.finished.emit(False, None, str(exc))

    def cancel(self) -> None:
        """Request cancellation of the image-loading worker."""
        self._cancel_requested = True


class RTStructLoadWorker(QtCore.QObject):
    """Background RTSTRUCT parser/mask extractor.

    RTSTRUCT extraction can be expensive because each ROI mask may require
    contour rasterization across the referenced CT/MR grid.  Running this work
    in a dedicated QThread keeps the viewer responsive while status/progress
    signals update the UI.
    """

    log = QtCore.Signal(str)
    progress = QtCore.Signal(int, int, str)
    status = QtCore.Signal(str)
    finished = QtCore.Signal(bool, object, str)

    def __init__(
        self,
        dicom_directory: str,
        rtstruct_path: str,
        volume_shape: Tuple[int, int, int],
        roi_colors: Sequence[Tuple[int, int, int]],
    ):
        """Initialize the background RTSTRUCT reader and mask extractor."""
        super().__init__()
        self.dicom_directory = dicom_directory
        self.rtstruct_path = rtstruct_path
        self.volume_shape = volume_shape
        self.roi_colors = tuple(roi_colors)
        self._cancel_requested = False

    @QtCore.Slot()
    def run(self) -> None:
        """Extract and align each RTSTRUCT ROI mask off the GUI thread."""
        try:
            self.progress.emit(0, 1, "Loading RTSTRUCT")
            self.status.emit(f"Loading RTSTRUCT: {os.path.basename(self.rtstruct_path)}")
            self.log.emit(f"Loading RTSTRUCT: {self.rtstruct_path}")

            rtstruct = RTStructBuilder.create_from(
                dicom_series_path=self.dicom_directory,
                rt_struct_path=self.rtstruct_path,
                warn_only=True,
            )

            roi_records: Dict[str, RoiRecord] = {}
            roi_names = rtstruct.get_roi_names()
            total_rois = max(1, len(roi_names))

            for index, name in enumerate(roi_names):
                if self._cancel_requested:
                    self.finished.emit(False, {}, "RTSTRUCT load cancelled.")
                    return

                try:
                    self.progress.emit(index, total_rois, "Loading RTSTRUCT contours")
                    self.status.emit(f"Loading RTSTRUCT ROI {index + 1} / {len(roi_names)}: {name}")

                    raw_mask = rtstruct.get_roi_mask_by_name(name)
                    mask = normalize_mask_from_rt_utils(raw_mask, self.volume_shape)
                    color = self.roi_colors[index % len(self.roi_colors)]
                    roi_records[name] = RoiRecord(name=name, mask=mask, color=color, enabled=True)
                    self.log.emit(f"Loaded ROI '{name}' with {int(mask.sum())} voxel(s).")
                except Exception as exc:
                    self.log.emit(f"Skipped ROI '{name}': {exc}")

            self.progress.emit(1, 1, "RTSTRUCT loaded")
            self.finished.emit(True, roi_records, "")
        except Exception as exc:
            self.finished.emit(False, {}, str(exc))

    def cancel(self) -> None:
        """Request cancellation of the RTSTRUCT-loading worker."""
        self._cancel_requested = True


class ImagePlaneWidget(QtWidgets.QWidget):
    slice_changed = QtCore.Signal()

    def __init__(self, title: str, parent: Optional[QtWidgets.QWidget] = None):
        """Build an image pane with a title, overlay, and slice slider."""
        super().__init__(parent)
        self.title = title
        self._slice_count = 0

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        header = QtWidgets.QHBoxLayout()
        self.title_label = QtWidgets.QLabel(title)
        self.title_label.setStyleSheet("font-weight: 700; color: #1f2933;")
        self.slice_label = QtWidgets.QLabel("Slice: -")
        self.slice_label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        header.addWidget(self.title_label)
        header.addStretch(1)
        header.addWidget(self.slice_label)
        layout.addLayout(header)

        self.graphics = pg.GraphicsLayoutWidget()
        self.view_box = self.graphics.addViewBox(lockAspect=True, enableMenu=True)
        self.view_box.setBackgroundColor("#05070a")
        self.view_box.invertY(True)

        self.image_item = pg.ImageItem(axisOrder="row-major")
        self.overlay_item = pg.ImageItem(axisOrder="row-major")
        self.overlay_item.setOpacity(1.0)

        self.view_box.addItem(self.image_item)
        self.view_box.addItem(self.overlay_item)
        layout.addWidget(self.graphics, stretch=1)

        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(0)
        self.slider.setEnabled(False)
        self.slider.valueChanged.connect(self._on_slider_changed)
        layout.addWidget(self.slider)

    def set_slice_count(self, count: int) -> None:
        """Set the number of available slices and center the slider."""
        self._slice_count = max(0, int(count))
        self.slider.blockSignals(True)
        self.slider.setMinimum(0)
        self.slider.setMaximum(max(0, self._slice_count - 1))
        self.slider.setEnabled(self._slice_count > 1)
        self.slider.setValue(max(0, self._slice_count // 2))
        self.slider.blockSignals(False)
        self.update_slice_label()

    def set_slice_index(self, index: int) -> None:
        """Move the slider to a clamped slice index."""
        if self._slice_count <= 0:
            return
        index = max(0, min(int(index), self._slice_count - 1))
        self.slider.setValue(index)

    def slice_index(self) -> int:
        """Return the current zero-based slice index."""
        return int(self.slider.value())

    def set_image(self, image: np.ndarray, levels: Tuple[float, float]) -> None:
        """Display a slice using the supplied intensity levels."""
        self.image_item.setImage(image, autoLevels=False, levels=levels)
        self.update_slice_label()

    def set_overlay(self, rgba: np.ndarray) -> None:
        """Display an RGBA contour overlay over the current slice."""
        self.overlay_item.setImage(rgba, autoLevels=False)

    def clear(self) -> None:
        """Clear the images and disable the slice slider."""
        self.image_item.clear()
        self.overlay_item.clear()
        self._slice_count = 0
        self.slider.blockSignals(True)
        self.slider.setMaximum(0)
        self.slider.setValue(0)
        self.slider.setEnabled(False)
        self.slider.blockSignals(False)
        self.update_slice_label()

    def auto_range(self) -> None:
        """Fit the view to the displayed image."""
        self.view_box.autoRange()

    def set_levels(self, levels: Tuple[float, float]) -> None:
        """Apply new window/level bounds to the image."""
        self.image_item.setLevels(levels)

    def update_slice_label(self) -> None:
        """Refresh the visible slice number and total."""
        if self._slice_count <= 0:
            self.slice_label.setText("Slice: -")
        else:
            self.slice_label.setText(f"Slice: {self.slice_index() + 1} / {self._slice_count}")

    def _on_slider_changed(self) -> None:
        """Update the label and notify listeners of a slider change."""
        self.update_slice_label()
        self.slice_changed.emit()


class RTStructPanel(QtWidgets.QWidget):
    """Fourth viewer pane dedicated to contour visibility controls."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        """Build the RTSTRUCT contour visibility controls."""
        super().__init__(parent)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        title = QtWidgets.QLabel("Contour RTSTRUCT")
        title.setStyleSheet("font-weight: 700; color: #1f2933;")
        layout.addWidget(title)

        controls = QtWidgets.QHBoxLayout()
        self.show_contours_checkbox = QtWidgets.QCheckBox("Show contours")
        self.show_contours_checkbox.setChecked(True)
        self.all_rois_button = QtWidgets.QPushButton("All")
        self.no_rois_button = QtWidgets.QPushButton("None")
        controls.addWidget(self.show_contours_checkbox)
        controls.addStretch(1)
        controls.addWidget(self.all_rois_button)
        controls.addWidget(self.no_rois_button)
        layout.addLayout(controls)

        self.roi_list = QtWidgets.QListWidget()
        self.roi_list.setAlternatingRowColors(True)
        layout.addWidget(self.roi_list, stretch=1)

        self.help_label = QtWidgets.QLabel("Loaded RTSTRUCT ROIs appear here. Toggle each contour on/off with the checkboxes.")
        self.help_label.setWordWrap(True)
        self.help_label.setStyleSheet("color: #52616f;")
        layout.addWidget(self.help_label)


class DicomViewerApp(QtWidgets.QMainWindow):
    ROI_COLORS: Tuple[Tuple[int, int, int], ...] = (
        (255, 82, 82),
        (0, 188, 212),
        (255, 193, 7),
        (76, 175, 80),
        (156, 39, 176),
        (255, 112, 67),
        (33, 150, 243),
        (205, 220, 57),
        (233, 30, 99),
        (0, 150, 136),
    )

    PRESETS: Dict[str, Tuple[float, float]] = {
        "CT Soft Tissue (WW 400 / WL 40)": (400.0, 40.0),
        "CT Lung (WW 1500 / WL -600)": (1500.0, -600.0),
        "CT Bone (WW 1800 / WL 400)": (1800.0, 400.0),
        "CT Brain (WW 80 / WL 40)": (80.0, 40.0),
        "MR Robust Full Range": (0.0, 0.0),
    }

    def __init__(self):
        """Initialize the viewer state, interface, and display settings."""
        super().__init__()
        self.setWindowTitle("Light DICOM Viewer - pyqtgraph")
        self.resize(1500, 920)

        self.state = ViewerState()
        self.current_thread: Optional[QtCore.QThread] = None
        self.current_worker: Optional[DicomLoadWorker] = None
        self.rtstruct_thread: Optional[QtCore.QThread] = None
        self.rtstruct_worker: Optional[RTStructLoadWorker] = None
        self.pending_rtstruct_path: str = ""
        self.current_levels: Tuple[float, float] = (0.0, 1.0)
        self._updating_controls = False

        self._build_ui()
        self._apply_style()
        self.reset_all()

    def _build_ui(self) -> None:
        """Construct image panes, contour controls, and viewer actions."""
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.setCentralWidget(splitter)

        controls = QtWidgets.QWidget()
        controls.setMinimumWidth(380)
        controls.setMaximumWidth(520)
        controls_layout = QtWidgets.QVBoxLayout(controls)
        controls_layout.setContentsMargins(14, 14, 14, 14)
        controls_layout.setSpacing(10)
        splitter.addWidget(controls)

        input_group = QtWidgets.QGroupBox("Input")
        input_layout = QtWidgets.QVBoxLayout(input_group)

        self.dicom_dir_edit = QtWidgets.QLineEdit()
        self.dicom_dir_edit.setReadOnly(True)
        self.load_dicom_button = QtWidgets.QPushButton("Load DICOM Image Directory")
        self.load_dicom_button.clicked.connect(self.select_dicom_directory)

        self.rtstruct_edit = QtWidgets.QLineEdit()
        self.rtstruct_edit.setReadOnly(True)
        self.rtstruct_edit.setPlaceholderText("RTSTRUCT auto-discovery status")

        self.progress_label = QtWidgets.QLabel("Idle")
        self.progress_label.setStyleSheet("color: #52616f;")
        self.load_progress = QtWidgets.QProgressBar()
        self.load_progress.setMinimum(0)
        self.load_progress.setMaximum(1)
        self.load_progress.setValue(0)
        self.load_progress.setTextVisible(True)

        input_layout.addWidget(self.load_dicom_button)
        input_layout.addWidget(self.dicom_dir_edit)
        input_layout.addWidget(QtWidgets.QLabel("RTSTRUCT:"))
        input_layout.addWidget(self.rtstruct_edit)
        input_layout.addWidget(self.progress_label)
        input_layout.addWidget(self.load_progress)
        controls_layout.addWidget(input_group)

        wl_group = QtWidgets.QGroupBox("Window / Level")
        wl_layout = QtWidgets.QVBoxLayout(wl_group)

        self.preset_combo = QtWidgets.QComboBox()
        self.preset_combo.addItems(list(self.PRESETS.keys()) + ["Robust 1-99% from volume"])
        self.preset_combo.currentTextChanged.connect(self.apply_selected_preset)
        wl_layout.addWidget(self.preset_combo)

        spin_layout = QtWidgets.QFormLayout()
        self.window_spin = QtWidgets.QDoubleSpinBox()
        self.window_spin.setRange(1.0, 100000.0)
        self.window_spin.setDecimals(1)
        self.window_spin.setSingleStep(25.0)
        self.window_spin.valueChanged.connect(self.update_levels_from_controls)

        self.level_spin = QtWidgets.QDoubleSpinBox()
        self.level_spin.setRange(-100000.0, 100000.0)
        self.level_spin.setDecimals(1)
        self.level_spin.setSingleStep(10.0)
        self.level_spin.valueChanged.connect(self.update_levels_from_controls)

        spin_layout.addRow("Window width:", self.window_spin)
        spin_layout.addRow("Level center:", self.level_spin)
        wl_layout.addLayout(spin_layout)

        fast_buttons = QtWidgets.QGridLayout()
        self.wide_button = QtWidgets.QPushButton("Wider")
        self.wide_button.clicked.connect(lambda: self.scale_window(1.25))
        self.narrow_button = QtWidgets.QPushButton("Narrower")
        self.narrow_button.clicked.connect(lambda: self.scale_window(0.80))
        self.level_up_button = QtWidgets.QPushButton("Level +")
        self.level_up_button.clicked.connect(lambda: self.shift_level(25.0))
        self.level_down_button = QtWidgets.QPushButton("Level -")
        self.level_down_button.clicked.connect(lambda: self.shift_level(-25.0))

        fast_buttons.addWidget(self.wide_button, 0, 0)
        fast_buttons.addWidget(self.narrow_button, 0, 1)
        fast_buttons.addWidget(self.level_up_button, 1, 0)
        fast_buttons.addWidget(self.level_down_button, 1, 1)
        wl_layout.addLayout(fast_buttons)

        controls_layout.addWidget(wl_group)

        controls_layout.addStretch(1)

        view_group = QtWidgets.QGroupBox("View")
        view_layout = QtWidgets.QVBoxLayout(view_group)

        self.reset_zoom_button = QtWidgets.QPushButton("Reset Zoom / Pan")
        self.reset_zoom_button.clicked.connect(self.reset_views)
        self.reset_slices_button = QtWidgets.QPushButton("Center All Slices")
        self.reset_slices_button.clicked.connect(self.center_slices)
        self.clear_button = QtWidgets.QPushButton("Clear Viewer")
        self.clear_button.clicked.connect(self.reset_all)

        view_layout.addWidget(self.reset_zoom_button)
        view_layout.addWidget(self.reset_slices_button)
        view_layout.addWidget(self.clear_button)

        controls_layout.addWidget(view_group)

        self.info_output = QtWidgets.QTextEdit()
        self.info_output.setReadOnly(True)
        self.info_output.setMinimumHeight(130)
        controls_layout.addWidget(self.info_output)

        viewer_container = QtWidgets.QWidget()
        viewer_layout = QtWidgets.QVBoxLayout(viewer_container)
        viewer_layout.setContentsMargins(8, 8, 8, 8)
        viewer_layout.setSpacing(8)

        header = QtWidgets.QHBoxLayout()
        self.viewer_title = QtWidgets.QLabel("DICOM viewer")
        self.viewer_title.setStyleSheet("font-size: 18px; font-weight: 700;")
        self.volume_label = QtWidgets.QLabel("No image loaded")
        self.volume_label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        header.addWidget(self.viewer_title)
        header.addStretch(1)
        header.addWidget(self.volume_label)
        viewer_layout.addLayout(header)

        self.grid = QtWidgets.QGridLayout()
        self.grid.setSpacing(8)
        viewer_layout.addLayout(self.grid, stretch=1)

        self.axial_panel = ImagePlaneWidget("Axial")
        self.sagittal_panel = ImagePlaneWidget("Sagittal")
        self.coronal_panel = ImagePlaneWidget("Coronal")
        self.rtstruct_panel = RTStructPanel()

        self.show_contours_checkbox = self.rtstruct_panel.show_contours_checkbox
        self.all_rois_button = self.rtstruct_panel.all_rois_button
        self.no_rois_button = self.rtstruct_panel.no_rois_button
        self.roi_list = self.rtstruct_panel.roi_list

        self.show_contours_checkbox.toggled.connect(self.update_all_views)
        self.all_rois_button.clicked.connect(lambda: self.set_all_rois(True))
        self.no_rois_button.clicked.connect(lambda: self.set_all_rois(False))
        self.roi_list.itemChanged.connect(self.on_roi_item_changed)

        self.axial_panel.slice_changed.connect(self.update_all_views)
        self.sagittal_panel.slice_changed.connect(self.update_all_views)
        self.coronal_panel.slice_changed.connect(self.update_all_views)

        self.grid.addWidget(self.axial_panel, 0, 0)
        self.grid.addWidget(self.sagittal_panel, 0, 1)
        self.grid.addWidget(self.coronal_panel, 1, 0)
        self.grid.addWidget(self.rtstruct_panel, 1, 1)

        splitter.addWidget(viewer_container)
        splitter.setSizes([430, 1070])

        self.statusBar().showMessage("Ready")

    def _apply_style(self) -> None:
        """Apply the viewer's Qt widget stylesheet."""
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background: #f5f7fb;
                color: #1f2933;
                font-size: 13px;
            }
            QGroupBox {
                border: 1px solid #ccd6e0;
                border-radius: 8px;
                margin-top: 12px;
                padding: 10px;
                font-weight: 600;
                background: #ffffff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 4px;
            }
            QPushButton {
                background: #1976d2;
                color: white;
                border: 0;
                border-radius: 5px;
                padding: 8px 10px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #1565c0;
            }
            QPushButton:pressed {
                background: #0d47a1;
            }
            QPushButton:disabled {
                background: #aeb8c2;
            }
            QLineEdit, QTextEdit, QListWidget, QComboBox, QDoubleSpinBox {
                background: #ffffff;
                border: 1px solid #cbd5df;
                border-radius: 5px;
                padding: 5px;
            }
            QCheckBox {
                spacing: 7px;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #d7e0ea;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #1976d2;
                width: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }
            """
        )

    def log(self, message: str) -> None:
        """Write a message to the log panel and status bar."""
        self.info_output.append(message)
        self.statusBar().showMessage(message, 7000)

    def select_dicom_directory(self) -> None:
        """Prompt for an image directory and start loading it."""
        selected = QtWidgets.QFileDialog.getExistingDirectory(self, "Select DICOM Image Directory")
        if not selected:
            return
        self.load_dicom_directory(selected)

    def load_dicom_directory(self, directory: str) -> None:
        """Start a background worker to scan and load a DICOM image directory."""
        if self.current_thread is not None:
            self.log("A DICOM load is already running.")
            return

        self.reset_all(clear_paths=False)
        self.dicom_dir_edit.setText(directory)
        self.set_loading_enabled(False)
        self.log(f"Loading DICOM image directory: {directory}")

        self.current_thread = QtCore.QThread(self)
        self.current_worker = DicomLoadWorker(directory)
        self.current_worker.moveToThread(self.current_thread)

        self.current_thread.started.connect(self.current_worker.run)
        self.current_worker.log.connect(self.log)
        self.current_worker.progress.connect(self.update_load_progress)
        self.current_worker.finished.connect(self.on_dicom_loaded)
        self.current_worker.finished.connect(self.current_thread.quit)
        self.current_worker.finished.connect(self.current_worker.deleteLater)
        self.current_thread.finished.connect(self.current_thread.deleteLater)
        self.current_thread.finished.connect(self.cleanup_worker_refs)

        self.current_thread.start()

    def update_load_progress(self, value: int, maximum: int, label: str) -> None:
        """Update the responsive load progress widgets from worker signals."""
        maximum = max(1, int(maximum))
        value = max(0, min(int(value), maximum))
        self.load_progress.setMaximum(maximum)
        self.load_progress.setValue(value)
        self.progress_label.setText(label)
        percent = int(round(100.0 * value / maximum))
        self.load_progress.setFormat(f"{label}: {percent}%")

    def on_dicom_loaded(self, success: bool, volume_data: Optional[VolumeData], error: str) -> None:
        """Handle a completed image load and update the viewer or show an error."""
        self.set_loading_enabled(True)

        if not success or volume_data is None:
            self.update_load_progress(0, 1, "Failed")
            self.log(f"Failed to load DICOM image directory: {error}")
            QtWidgets.QMessageBox.warning(self, "DICOM Load Failed", error)
            return

        self.state.volume_data = volume_data
        self.state.rois.clear()
        self.roi_list.clear()
        self.rtstruct_edit.clear()

        volume = volume_data.volume
        self.axial_panel.set_slice_count(volume.shape[0])
        self.sagittal_panel.set_slice_count(volume.shape[2])
        self.coronal_panel.set_slice_count(volume.shape[1])

        width, level = default_window_level(volume)
        self.set_window_level(width, level)

        self.viewer_title.setText(volume_data.description or "DICOM viewer")
        self.volume_label.setText(
            f"{volume.shape[2]} x {volume.shape[1]} x {volume.shape[0]} | "
            f"spacing z/y/x {volume_data.spacing_zyx[0]:.3g}/{volume_data.spacing_zyx[1]:.3g}/{volume_data.spacing_zyx[2]:.3g}"
        )

        self.update_all_views()
        self.reset_views()
        self.update_load_progress(1, 1, "Image volume loaded")
        self.log(f"Loaded image volume: {volume.shape[0]} slices, shape z/y/x = {volume.shape}")
        self.log(f"Modality: {volume_data.modality}; patient position: {volume_data.patient_position or 'unknown'}")
        QtCore.QTimer.singleShot(0, self.load_discovered_rtstruct)

    def load_discovered_rtstruct(self) -> None:
        """Automatically load discovered RTSTRUCTs or prompt when ambiguous."""
        volume_data = self.state.volume_data
        if volume_data is None:
            return

        paths = volume_data.rtstruct_paths
        if not paths:
            self.rtstruct_edit.setText("No RTSTRUCT discovered in selected directory.")
            self.log("No RTSTRUCT discovered during DICOM scan.")
            return

        if len(paths) == 1:
            selected = paths[0]
            self.log(f"Auto-loading discovered RTSTRUCT: {selected}")
        else:
            display_items = [f"{index + 1}. {os.path.basename(path)} — {path}" for index, path in enumerate(paths)]
            selected_item, accepted = QtWidgets.QInputDialog.getItem(
                self,
                "Select RTSTRUCT",
                "Multiple RTSTRUCT files were discovered. Select one to load:",
                display_items,
                0,
                False,
            )
            if not accepted or not selected_item:
                self.rtstruct_edit.setText(f"{len(paths)} RTSTRUCT files discovered; none selected.")
                self.log("Multiple RTSTRUCT files discovered; user did not select one.")
                return

            selected = paths[display_items.index(selected_item)]
            self.log(f"Loading selected RTSTRUCT: {selected}")

        self.load_rtstruct(selected)

    def load_rtstruct(self, rtstruct_path: str) -> None:
        """Start background extraction of contours from an RTSTRUCT file."""
        if self.state.volume_data is None:
            self.log("Load a DICOM image directory before loading an RTSTRUCT.")
            return

        if self.rtstruct_thread is not None:
            self.log("An RTSTRUCT load is already running.")
            return

        self.pending_rtstruct_path = rtstruct_path
        self.state.rois.clear()
        self.roi_list.clear()
        self.rtstruct_edit.setText(f"Loading: {rtstruct_path}")
        self.update_load_progress(0, 1, "Loading RTSTRUCT")
        self.statusBar().showMessage(f"Loading RTSTRUCT: {os.path.basename(rtstruct_path)}")
        self.set_loading_enabled(False)

        self.rtstruct_thread = QtCore.QThread(self)
        self.rtstruct_worker = RTStructLoadWorker(
            dicom_directory=self.state.volume_data.directory,
            rtstruct_path=rtstruct_path,
            volume_shape=self.state.volume_data.volume.shape,
            roi_colors=self.ROI_COLORS,
        )
        self.rtstruct_worker.moveToThread(self.rtstruct_thread)

        self.rtstruct_thread.started.connect(self.rtstruct_worker.run)
        self.rtstruct_worker.log.connect(self.log)
        self.rtstruct_worker.progress.connect(self.update_load_progress)
        self.rtstruct_worker.status.connect(self.statusBar().showMessage)
        self.rtstruct_worker.finished.connect(self.on_rtstruct_loaded)
        self.rtstruct_worker.finished.connect(self.rtstruct_thread.quit)
        self.rtstruct_worker.finished.connect(self.rtstruct_worker.deleteLater)
        self.rtstruct_thread.finished.connect(self.rtstruct_thread.deleteLater)
        self.rtstruct_thread.finished.connect(self.cleanup_rtstruct_worker_refs)

        self.rtstruct_thread.start()

    def on_rtstruct_loaded(self, success: bool, rois: object, error: str) -> None:
        """Populate the ROI controls after contour extraction or report a failure."""
        self.set_loading_enabled(True)

        if not success:
            self.update_load_progress(0, 1, "RTSTRUCT failed")
            self.rtstruct_edit.setText("RTSTRUCT load failed")
            self.log(f"Failed to load RTSTRUCT: {error}")
            QtWidgets.QMessageBox.warning(self, "RTSTRUCT Load Failed", error)
            return

        self.state.rois = dict(sorted(dict(rois).items(), key=lambda item: item[0].casefold()))
        self.roi_list.blockSignals(True)
        self.roi_list.clear()
        for roi in self.state.rois.values():
            item = QtWidgets.QListWidgetItem(roi.name)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.Checked if roi.enabled else QtCore.Qt.Unchecked)
            item.setForeground(QtGui.QBrush(QtGui.QColor(*roi.color)))
            self.roi_list.addItem(item)
        self.roi_list.blockSignals(False)

        self.rtstruct_edit.setText(self.pending_rtstruct_path)
        self.update_all_views()
        self.update_load_progress(1, 1, "RTSTRUCT loaded")
        self.statusBar().showMessage(f"Loaded {len(self.state.rois)} RTSTRUCT ROI(s). Toggle contours in the RTSTRUCT pane.", 7000)
        self.log(f"Loaded {len(self.state.rois)} RTSTRUCT ROI(s). Toggle contour visibility in the lower-right RTSTRUCT pane.")

    def set_all_rois(self, enabled: bool) -> None:
        """Set visibility of every loaded ROI and refresh image overlays."""
        self.roi_list.blockSignals(True)
        for row in range(self.roi_list.count()):
            item = self.roi_list.item(row)
            item.setCheckState(QtCore.Qt.Checked if enabled else QtCore.Qt.Unchecked)
            roi = self.state.rois.get(item.text())
            if roi is not None:
                roi.enabled = enabled
        self.roi_list.blockSignals(False)
        self.update_all_views()

    def on_roi_item_changed(self, item: QtWidgets.QListWidgetItem) -> None:
        """Synchronize an ROI checkbox with the displayed overlays."""
        roi = self.state.rois.get(item.text())
        if roi is None:
            return
        roi.enabled = item.checkState() == QtCore.Qt.Checked
        self.update_all_views()

    def apply_selected_preset(self, text: str) -> None:
        """Apply the selected intensity window/level preset."""
        if self._updating_controls:
            return

        if self.state.volume_data is None:
            return

        if text == "Robust 1-99% from volume" or self.PRESETS.get(text, (0.0, 0.0))[0] == 0.0:
            width, level = default_window_level(self.state.volume_data.volume)
        else:
            width, level = self.PRESETS[text]

        self.set_window_level(width, level)

    def update_levels_from_controls(self) -> None:
        """Apply window and level values entered in the numeric controls."""
        if self._updating_controls:
            return
        self.set_window_level(float(self.window_spin.value()), float(self.level_spin.value()))

    def scale_window(self, factor: float) -> None:
        """Multiply the current window width by a factor."""
        self.set_window_level(max(1.0, float(self.window_spin.value()) * factor), float(self.level_spin.value()))

    def shift_level(self, shift: float) -> None:
        """Offset the current window center by the requested amount."""
        self.set_window_level(float(self.window_spin.value()), float(self.level_spin.value()) + shift)

    def set_window_level(self, width: float, level: float) -> None:
        """Update intensity bounds and keep numeric controls in sync."""
        width = max(1.0, float(width))
        level = float(level)
        low = level - width / 2.0
        high = level + width / 2.0
        self.current_levels = (low, high)

        self._updating_controls = True
        self.window_spin.setValue(width)
        self.level_spin.setValue(level)
        self._updating_controls = False

        for panel in (self.axial_panel, self.sagittal_panel, self.coronal_panel):
            panel.set_levels(self.current_levels)

        self.statusBar().showMessage(f"Window/level: WW {width:.1f}, WL {level:.1f}", 3000)

    def update_all_views(self) -> None:
        """Render current axial, sagittal, and coronal slices and overlays."""
        volume_data = self.state.volume_data
        if volume_data is None:
            return

        volume = volume_data.volume

        z = self.axial_panel.slice_index()
        x = self.sagittal_panel.slice_index()
        y = self.coronal_panel.slice_index()

        z = max(0, min(z, volume.shape[0] - 1))
        y = max(0, min(y, volume.shape[1] - 1))
        x = max(0, min(x, volume.shape[2] - 1))

        self.axial_panel.set_image(volume[z, :, :], self.current_levels)
        self.sagittal_panel.set_image(volume[:, :, x], self.current_levels)
        self.coronal_panel.set_image(volume[:, y, :], self.current_levels)

        if self.show_contours_checkbox.isChecked():
            enabled_rois = [roi for roi in self.state.rois.values() if roi.enabled]
            axial_masks = [(roi.mask[z, :, :], roi.color) for roi in enabled_rois]
            sagittal_masks = [(roi.mask[:, :, x], roi.color) for roi in enabled_rois]
            coronal_masks = [(roi.mask[:, y, :], roi.color) for roi in enabled_rois]

            self.axial_panel.set_overlay(blend_overlays(volume[z, :, :].shape, axial_masks))
            self.sagittal_panel.set_overlay(blend_overlays(volume[:, :, x].shape, sagittal_masks))
            self.coronal_panel.set_overlay(blend_overlays(volume[:, y, :].shape, coronal_masks))
        else:
            self.axial_panel.set_overlay(np.zeros(volume[z, :, :].shape + (4,), dtype=np.ubyte))
            self.sagittal_panel.set_overlay(np.zeros(volume[:, :, x].shape + (4,), dtype=np.ubyte))
            self.coronal_panel.set_overlay(np.zeros(volume[:, y, :].shape + (4,), dtype=np.ubyte))

    def reset_views(self) -> None:
        """Fit all three image panes to their current contents."""
        for panel in (self.axial_panel, self.sagittal_panel, self.coronal_panel):
            panel.auto_range()

    def center_slices(self) -> None:
        """Move each slice slider to the center of the loaded volume."""
        volume_data = self.state.volume_data
        if volume_data is None:
            return
        z_count, y_count, x_count = volume_data.volume.shape
        self.axial_panel.set_slice_index(z_count // 2)
        self.sagittal_panel.set_slice_index(x_count // 2)
        self.coronal_panel.set_slice_index(y_count // 2)
        self.update_all_views()

    def reset_all(self, clear_paths: bool = True) -> None:
        """Clear displayed data and request cancellation of active workers."""
        if self.current_worker is not None:
            self.current_worker.cancel()
        if self.rtstruct_worker is not None:
            self.rtstruct_worker.cancel()

        self.state = ViewerState()
        self.current_levels = (0.0, 1.0)

        self.axial_panel.clear()
        self.sagittal_panel.clear()
        self.coronal_panel.clear()
        self.roi_list.clear()
        self.info_output.clear()

        if clear_paths:
            self.dicom_dir_edit.clear()
            self.rtstruct_edit.clear()

        self.viewer_title.setText("DICOM viewer")
        self.volume_label.setText("No image loaded")
        self.statusBar().showMessage("Ready")

    def set_loading_enabled(self, enabled: bool) -> None:
        """Enable or disable loading and clearing controls."""
        self.load_dicom_button.setEnabled(enabled)
        self.clear_button.setEnabled(enabled)

    def cleanup_worker_refs(self) -> None:
        """Release references after the DICOM image worker finishes."""
        self.current_thread = None
        self.current_worker = None

    def cleanup_rtstruct_worker_refs(self) -> None:
        """Release references after the RTSTRUCT worker finishes."""
        self.rtstruct_thread = None
        self.rtstruct_worker = None

    def closeEvent(self, event) -> None:
        """Request worker cancellation and wait briefly before closing."""
        if self.current_worker is not None:
            self.current_worker.cancel()
        if self.rtstruct_worker is not None:
            self.rtstruct_worker.cancel()
        if self.current_thread is not None and self.current_thread.isRunning():
            self.current_thread.quit()
            self.current_thread.wait(3000)
        if self.rtstruct_thread is not None and self.rtstruct_thread.isRunning():
            self.rtstruct_thread.quit()
            self.rtstruct_thread.wait(3000)
        super().closeEvent(event)


def main() -> None:
    """Configure Qt and launch the DICOM viewer desktop application."""
    configure_qt_plugin_paths()
    QtCore.QCoreApplication.setLibraryPaths(
        [os.environ["QT_PLUGIN_PATH"]]
        if os.environ.get("QT_PLUGIN_PATH")
        else QtCore.QCoreApplication.libraryPaths()
    )

    app = QtWidgets.QApplication(sys.argv)
    window = DicomViewerApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
