"""Optional three-plane CT overlays for approved contour comparisons."""

import os

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
import numpy as np
import SimpleITK as sitk
from skimage.measure import find_contours

from dcmrtstruct2nii.adapters.convert.filenameconverter import FilenameConverter


def plot_comparison(row, output_dir, index):
    """Save a CT figure with solid ground truth and dashed comparison contours.

    The converter writes image.nii.gz beside each mask. Read the image beside
    the chosen ground truth, falling back to the other mask's image if needed.
    """
    gt_side = int(row["ground_truth"])
    if gt_side not in (1, 2):
        raise ValueError("Ground truth must be side 1 or 2.")
    gt_path = row[f"path_{gt_side}"]
    pred_path = row[f"path_{3 - gt_side}"]
    for path in (gt_path, pred_path):
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Missing converted mask: {path}")

    image_candidates = [
        os.path.join(os.path.dirname(path), "image.nii.gz")
        for path in (gt_path, pred_path)
    ]
    image_path = next((path for path in image_candidates if os.path.isfile(path)), None)
    if image_path is None:
        raise FileNotFoundError(f"Missing converted CT image: {image_candidates}")

    gt = sitk.ReadImage(gt_path)
    pred = sitk.ReadImage(pred_path)
    image = sitk.ReadImage(image_path)
    if any(volume.GetDimension() != 3 for volume in (gt, pred, image)):
        raise ValueError("CT image and both masks must be 3D.")

    # Match masks in physical space before finding a shared crop.
    pred = sitk.Resample(pred, gt, sitk.Transform(), sitk.sitkNearestNeighbor,
                         0, pred.GetPixelID())
    gt_array = sitk.GetArrayFromImage(gt) > 0
    pred_array = sitk.GetArrayFromImage(pred) > 0
    union = gt_array | pred_array
    if not np.any(union):
        raise ValueError("Cannot plot two empty masks.")

    # Follow the reference's fixed-size crop centered on the union of masks,
    # but resample only the cropped CT region to conserve memory.
    positions = np.argwhere(union)
    center = (positions.min(axis=0) + positions.max(axis=0)) // 2
    half_width = 100
    start = np.maximum(center - half_width, 0)
    stop = np.minimum(center + half_width + 1, union.shape)
    slices = tuple(slice(int(lo), int(hi)) for lo, hi in zip(start, stop))
    cropped_gt = gt_array[slices]
    cropped_pred = pred_array[slices]
    cropped_union = union[slices]

    index_xyz = [int(value) for value in start[::-1]]
    size_xyz = [int(value) for value in (stop - start)[::-1]]
    gt_roi = sitk.RegionOfInterest(gt, size_xyz, index_xyz)
    ct_roi = sitk.Resample(image, gt_roi, sitk.Transform(), sitk.sitkLinear,
                           -1000.0, sitk.sitkFloat32)
    ct_array = np.clip(sitk.GetArrayFromImage(ct_roi), -300, 400)

    planes = (
        ("Axial", 0, (1, 2)),
        ("Coronal", 1, (0, 2)),
        ("Sagittal", 2, (0, 1)),
    )
    figure = Figure(figsize=(15, 5))
    FigureCanvasAgg(figure)
    axes = figure.subplots(1, 3)
    for axis, (title, plane_axis, sum_axes) in zip(axes, planes):
        totals = cropped_union.sum(axis=sum_axes)
        plane_index = int(np.argmax(totals))
        ct_plane = np.take(ct_array, plane_index, axis=plane_axis)
        gt_plane = np.take(cropped_gt, plane_index, axis=plane_axis)
        pred_plane = np.take(cropped_pred, plane_index, axis=plane_axis)
        axis.imshow(ct_plane, cmap="gray", vmin=-300, vmax=400)
        for plane, color, style, label in (
            (gt_plane, "blue", "solid", "Ground truth"),
            (pred_plane, "red", "dashed", "Comparison"),
        ):
            for polygon in find_contours(plane.astype(float), level=0.5):
                axis.plot(polygon[:, 1], polygon[:, 0], color=color,
                          linestyle=style, linewidth=1.5, label=label)
                label = None
        axis.set_title(title)
        axis.axis("off")

    handles, labels = axes[0].get_legend_handles_labels()
    if handles:
        figure.legend(handles, labels, loc="upper right")
    figure.suptitle(
        f"{row[f'contour_name_{gt_side}']} (ground truth) vs "
        f"{row[f'contour_name_{3 - gt_side}']}"
    )
    figure.tight_layout(rect=(0, 0, 0.9, 0.93))

    os.makedirs(output_dir, exist_ok=True)
    converter = FilenameConverter()
    name = converter.convert(
        f"{row['contour_name_1']}_vs_{row['contour_name_2']}"
    )
    output_path = os.path.join(output_dir, f"{index:04d}_{name}.png")
    figure.savefig(output_path, dpi=150)
    figure.clear()
    return output_path