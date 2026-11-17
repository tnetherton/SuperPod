"""Selection, pairing, and SimpleITK metrics for the contour comparison GUI."""

from itertools import combinations
import os

import numpy as np
import pandas as pd
import pydicom
import SimpleITK as sitk
from dcmrtstruct2nii.adapters.convert.filenameconverter import FilenameConverter


COMPARISON_COLUMNS = [
    "contour_name_1", "structure_file_1", "path_1",
    "contour_name_2", "structure_file_2", "path_2", "ground_truth",
]
METRIC_COLUMNS = COMPARISON_COLUMNS + ["dsc", "msd", "dsc-gt-voi", "msd-gt-voi", "status"]


def selected_dicom_log(log):
    """Keep the selected RTSTRUCTs and their referenced CT series only.

    A referenced CT SOP UID identifies the series; the *whole* series is kept
    because the converter needs all its slices. If no image references exist,
    a unique CT series with the same FrameOfReferenceUID is required.
    """
    selected_rs = log[(log["Modality"] == "RTSTRUCT") & (log["selected"] != "")].copy()
    if selected_rs.empty:
        raise ValueError("Select at least one RTSTRUCT contour.")
    ct = log[log["Modality"] == "CT"].copy()
    if ct.empty:
        raise ValueError("No CT files were found in the selected directory.")

    ct_info = {}
    series = {}
    for _, row in ct.iterrows():
        ds = pydicom.dcmread(row["Path"], stop_before_pixels=True)
        uid = str(ds.get("SeriesInstanceUID", ""))
        ct_info[row["Path"]] = (uid, str(ds.get("SOPInstanceUID", "")),
                                str(ds.get("FrameOfReferenceUID", "")))
        series.setdefault(uid, set()).add(row["Path"])

    included_ct = set()
    for _, row in selected_rs.iterrows():
        ds = pydicom.dcmread(row["Path"], stop_before_pixels=True)
        frame = str(ds.get("FrameOfReferenceUID", ""))
        selected_names = set(row["selected"].split(", "))
        selected_numbers = {
            int(roi.ROINumber) for roi in ds.get("StructureSetROISequence", [])
            if roi.ROIName in selected_names
        }
        roi_frames = {
            str(roi.get("ReferencedFrameOfReferenceUID", ""))
            for roi in ds.get("StructureSetROISequence", [])
            if int(roi.ROINumber) in selected_numbers
        }
        roi_frames.discard("")
        if len(roi_frames) > 1:
            raise ValueError(f"Selected contours in {row['FileName']} use different frames.")
        if frame and roi_frames and frame not in roi_frames:
            raise ValueError(f"Selected contours in {row['FileName']} disagree on frame of reference.")
        frame = frame or next(iter(roi_frames), "")
        referenced = set()
        for roi in ds.get("ROIContourSequence", []):
            if int(roi.ReferencedROINumber) not in selected_numbers:
                continue
            for contour in roi.get("ContourSequence", []):
                for image in contour.get("ContourImageSequence", []):
                    referenced.add(str(image.get("ReferencedSOPInstanceUID", "")))
        # Use the RTSTRUCT's general image references only when the selected
        # contours have no image references of their own.
        if not referenced:
            for reference in ds.get("ReferencedFrameOfReferenceSequence", []):
                if frame and str(reference.get("FrameOfReferenceUID", "")) != frame:
                    continue
                for study in reference.get("RTReferencedStudySequence", []):
                    for ref_series in study.get("RTReferencedSeriesSequence", []):
                        for image in ref_series.get("ContourImageSequence", []):
                            referenced.add(str(image.get("ReferencedSOPInstanceUID", "")))
        referenced.discard("")

        matched = {
            uid for uid, sop, ct_frame in ct_info.values()
            if sop in referenced and (not frame or ct_frame == frame)
        }
        if referenced and not matched:
            raise ValueError(f"No referenced CT images found for {row['FileName']}.")
        if not referenced:
            matched = {
                uid for uid, _, ct_frame in ct_info.values()
                if frame and ct_frame == frame
            }
        if len(matched) != 1 or "" in matched:
            raise ValueError(
                f"Cannot uniquely pair {row['FileName']} with a CT series; "
                "check its CT references and FrameOfReferenceUID."
            )
        included_ct.update(series[next(iter(matched))])

    selected_ct = ct[ct["Path"].isin(included_ct)].copy()
    selected_ct["selected"] = ""
    selected_rs["StructureNames"] = selected_rs["selected"]
    return pd.concat([selected_ct, selected_rs], ignore_index=True)[
        ["FileName", "Path", "Modality", "StructureNames", "selected"]
    ]


def build_comparison_list(log, temp_dir):
    """One unordered pair per two distinct (RTSTRUCT file, contour name) selections."""
    rs = log[(log["Modality"] == "RTSTRUCT") & (log["selected"] != "")]
    selected = []
    converter = FilenameConverter()
    for _, row in rs.iterrows():
        output_dir = os.path.join(temp_dir, row["FileName"].replace(".dcm", ""))
        for name in row["selected"].split(", "):
            mask = os.path.abspath(os.path.join(
                output_dir, converter.convert(f"mask_{name}") + ".nii.gz"
            ))
            selected.append((name, row["FileName"], mask))
    rows = [
        dict(zip(COMPARISON_COLUMNS, (
            first[0], first[1], first[2], second[0], second[1], second[2], 1
        )))
        for first, second in combinations(selected, 2)
    ]
    return pd.DataFrame(rows, columns=COMPARISON_COLUMNS)


def _geometry_matches(first, second):
    return (first.GetSize() == second.GetSize()
            and np.allclose(first.GetOrigin(), second.GetOrigin(), atol=1e-4)
            and np.allclose(first.GetSpacing(), second.GetSpacing(), atol=1e-4)
            and np.allclose(first.GetDirection(), second.GetDirection(), atol=1e-4))


def _measure_aligned_masks(gt, pred):
    """Measure two aligned binary masks, cropping to their shared occupied region."""
    gt_array = sitk.GetArrayViewFromImage(gt)
    pred_array = sitk.GetArrayViewFromImage(pred)
    gt_present = bool(np.any(gt_array))
    pred_present = bool(np.any(pred_array))
    if not gt_present and not pred_present:
        return (float("nan"), float("nan"))
    if not gt_present or not pred_present:
        return (0.0, float("nan"))

    # Crop both masks to the *union* of their nonzero voxels, leaving a
    # one-voxel margin where available. ROI preserves the physical geometry.
    occupied = np.argwhere(np.logical_or(gt_array, pred_array))
    lower = np.maximum(occupied.min(axis=0) - 1, 0)
    upper = np.minimum(occupied.max(axis=0) + 2, gt_array.shape)
    index = [int(v) for v in lower[::-1]]
    size = [int(v) for v in (upper - lower)[::-1]]
    gt = sitk.RegionOfInterest(gt, size, index)
    pred = sitk.RegionOfInterest(pred, size, index)

    overlap = sitk.LabelOverlapMeasuresImageFilter()
    overlap.Execute(gt, pred)
    dsc = overlap.GetDiceCoefficient()

    gt_contour = sitk.LabelContour(gt)
    pred_contour = sitk.LabelContour(pred)
    gt_surface = sitk.GetArrayFromImage(gt_contour) > 0
    pred_surface = sitk.GetArrayFromImage(pred_contour) > 0
    # Distance to the opposing *surface*, not to the opposing foreground.
    gt_distance = sitk.GetArrayFromImage(
        sitk.Abs(sitk.SignedMaurerDistanceMap(
            gt_contour, squaredDistance=False, useImageSpacing=True
        ))
    )
    pred_distance = sitk.GetArrayFromImage(
        sitk.Abs(sitk.SignedMaurerDistanceMap(
            pred_contour, squaredDistance=False, useImageSpacing=True
        ))
    )
    msd = (float(gt_distance[pred_surface].mean())
           + float(pred_distance[gt_surface].mean())) / 2
    return float(dsc), msd


def compare_masks_with_gt_voi(ground_truth_path, prediction_path):
    """Return full DSC/MSD and DSC/MSD restricted to the ground-truth 3D box.

    The VOI is the tight, axis-aligned bounding box of nonzero GT voxels on
    the GT grid. Prediction voxels outside it are ignored. A one-voxel zero
    border is added after cropping so surface measurements remain defined at
    the box edges without including prediction outside the VOI.
    """
    gt = sitk.ReadImage(ground_truth_path)
    pred = sitk.ReadImage(prediction_path)
    if gt.GetDimension() != 3 or pred.GetDimension() != 3:
        raise ValueError("Both masks must be 3D.")
    if not _geometry_matches(gt, pred):
        pred = sitk.Resample(pred, gt, sitk.Transform(), sitk.sitkNearestNeighbor,
                             0, pred.GetPixelID())

    gt = sitk.Cast(gt > 0, sitk.sitkUInt8)
    pred = sitk.Cast(pred > 0, sitk.sitkUInt8)
    gt_indices = np.argwhere(sitk.GetArrayViewFromImage(gt) > 0)
    if gt_indices.size:
        lower = gt_indices.min(axis=0)
        upper = gt_indices.max(axis=0) + 1
        index = [int(v) for v in lower[::-1]]
        size = [int(v) for v in (upper - lower)[::-1]]
        gt_voi = sitk.RegionOfInterest(gt, size, index)
        pred_voi = sitk.RegionOfInterest(pred, size, index)
        gt_voi = sitk.ConstantPad(gt_voi, [1, 1, 1], [1, 1, 1], 0)
        pred_voi = sitk.ConstantPad(pred_voi, [1, 1, 1], [1, 1, 1], 0)
    else:
        gt_voi = pred_voi = None

    full = _measure_aligned_masks(gt, pred)
    voi = (_measure_aligned_masks(gt_voi, pred_voi)
           if gt_voi is not None else (float("nan"), float("nan")))
    return full + voi


def compare_masks(ground_truth_path, prediction_path):
    """Return the existing full-mask Dice and symmetric mean surface distance."""
    return compare_masks_with_gt_voi(ground_truth_path, prediction_path)[:2]


def calculate_metrics(comparisons):
    """Return one result row per approved comparison, including failures."""
    results = []
    for _, row in comparisons.iterrows():
        result = row.to_dict()
        result.update(dsc=float("nan"), msd=float("nan"),
                      **{"dsc-gt-voi": float("nan"), "msd-gt-voi": float("nan")},
                      status="ok")
        try:
            gt_side = int(row["ground_truth"])
            if gt_side not in (1, 2):
                raise ValueError("Ground truth must be side 1 or 2.")
            gt_path = row[f"path_{gt_side}"]
            pred_path = row[f"path_{3 - gt_side}"]
            for path in (gt_path, pred_path):
                if not os.path.isfile(path):
                    raise FileNotFoundError(f"Missing converted mask: {path}")
            (result["dsc"], result["msd"],
             result["dsc-gt-voi"], result["msd-gt-voi"]) = (
                compare_masks_with_gt_voi(gt_path, pred_path)
            )
            if np.isnan(result["msd"]) or np.isnan(result["msd-gt-voi"]):
                result["status"] = "empty mask in full image or GT VOI"
        except Exception as exc:
            result["status"] = str(exc)
        results.append(result)
    return pd.DataFrame(results, columns=METRIC_COLUMNS)