"""
Helpers for per-well RGB measurement and color-delta CSV export.
"""
from __future__ import annotations

import csv
import math
import os

from datetime import datetime

try:
    import cv2
except ImportError:
    cv2 = None

try:
    import numpy as np
except ImportError:
    np = None

import module_well_location_helper as WL


RGB_DECIMALS = 3
TIME_DECIMALS = 3
DELTA_DECIMALS = 2
DEFAULT_TRIM_PERCENT = 10


def get_unique_id():
    current_time = datetime.now()
    return current_time.strftime("%Y-%m-%d_%H%M%S")


def format_number(value, decimals):
    if value is None:
        return ""

    numeric_value = float(value)
    if abs(numeric_value) < 1e-12:
        numeric_value = 0.0

    text = f"{numeric_value:.{decimals}f}".rstrip("0").rstrip(".")
    return text or "0"


def calculate_color_delta(control_rgb, experimental_rgb):
    r0, g0, b0 = control_rgb
    r1, g1, b1 = experimental_rgb
    return math.sqrt(((r0 - r1) ** 2) + ((g0 - g1) ** 2) + ((b0 - b1) ** 2))


def normalize_trim_percent(value, default=DEFAULT_TRIM_PERCENT):
    if value is None:
        return int(default)

    try:
        trim_percent = int(value)
    except (TypeError, ValueError):
        return int(default)

    return max(trim_percent, 0)


def _require_image_stack():
    if cv2 is None or np is None:
        raise RuntimeError("OpenCV and numpy are required for color assay measurement.")


def _load_image(image_path):
    _require_image_stack()
    image = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
    if image is None:
        raise RuntimeError(f"Unable to read image for color assay: {image_path}")
    return image


def _get_visible_bgr_pixels(image, capture_state=None):
    _require_image_stack()

    if image.ndim == 2:
        image = np.stack((image, image, image), axis=-1)

    if image.ndim != 3:
        raise RuntimeError(f"Unsupported image shape for color assay: {image.shape}")

    if image.shape[2] == 4:
        alpha_mask = image[..., 3] > 0
        if not np.any(alpha_mask):
            raise RuntimeError("Image alpha mask contains no visible pixels.")
        return image[..., :3][alpha_mask]

    if image.shape[2] != 3:
        raise RuntimeError(f"Unsupported channel count for color assay: {image.shape[2]}")

    if capture_state is None:
        raise RuntimeError("capture_state is required to measure uncropped well images.")

    preview_size = capture_state.get("preview_size")
    radius = capture_state.get("radius")
    line_thickness = capture_state.get("line_thickness", 1)
    if preview_size is None or radius is None:
        raise RuntimeError("capture_state must include preview_size and radius.")

    cropped_image = WL.crop_image_to_crosshair_circle(
        image,
        preview_size=preview_size,
        radius=radius,
        line_thickness=line_thickness,
    )
    alpha_mask = cropped_image[..., 3] > 0
    if not np.any(alpha_mask):
        raise RuntimeError("Cropped image contains no visible pixels inside the ROI.")
    return cropped_image[..., :3][alpha_mask]


def _calculate_trimmed_mean(channel_values, trim_percent):
    sorted_values = np.sort(np.asarray(channel_values, dtype=np.float64))
    if sorted_values.size == 0:
        raise RuntimeError("No visible pixels were available for trimmed-mean measurement.")

    trim_percent = normalize_trim_percent(trim_percent, default=0)
    if trim_percent <= 0 or sorted_values.size == 1:
        return float(sorted_values.mean())

    trim_count = int(np.floor(sorted_values.size * (trim_percent / 100.0)))
    max_trim_count = (sorted_values.size - 1) // 2
    trim_count = min(trim_count, max_trim_count)

    if trim_count > 0:
        sorted_values = sorted_values[trim_count:sorted_values.size - trim_count]

    return float(sorted_values.mean())


def measure_mean_rgb(image_path, capture_state=None, trim_percent=DEFAULT_TRIM_PERCENT):
    image = _load_image(image_path)
    visible_bgr = _get_visible_bgr_pixels(image, capture_state=capture_state)
    trimmed_bgr = [
        _calculate_trimmed_mean(visible_bgr[:, channel_index], trim_percent)
        for channel_index in range(3)
    ]
    return (trimmed_bgr[2], trimmed_bgr[1], trimmed_bgr[0])


class ColorAssayTracker:
    def __init__(self, save_folder, total_wells, csv_path=None, trim_percent=DEFAULT_TRIM_PERCENT):
        self.save_folder = save_folder
        self.total_wells = int(total_wells)
        self.baselines = {}
        self.trim_percent = normalize_trim_percent(trim_percent)
        self.csv_path = csv_path or os.path.join(
            save_folder,
            f"color_assay_{get_unique_id()}.csv",
        )
        self._init_csv_file()

    def _build_header_rows(self):
        header_row_1 = []
        header_row_2 = []

        for well_number in range(1, self.total_wells + 1):
            header_row_1.extend([f"Well {well_number}", "", "", "", ""])
            header_row_2.extend(["Time (min)", "R", "G", "B", "Δcolor"])
            if well_number < self.total_wells:
                header_row_1.append("")
                header_row_2.append("")

        return header_row_1, header_row_2

    def _init_csv_file(self):
        header_row_1, header_row_2 = self._build_header_rows()
        with open(self.csv_path, "w", newline="", encoding="utf-8") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(header_row_1)
            writer.writerow(header_row_2)

    def build_blank_well_block(self):
        return ["", "", "", "", ""]

    def build_well_block(self, well_number, time_min, image_path, capture_state=None, current_round=1):
        try:
            rgb = measure_mean_rgb(
                image_path,
                capture_state=capture_state,
                trim_percent=self.trim_percent,
            )
        except Exception as exc:
            print(f"Color assay measurement failed for well {well_number}: {exc}")
            return self.build_blank_well_block()

        baseline = self.baselines.get(well_number)
        if baseline is None:
            if int(current_round) == 1:
                self.baselines[well_number] = rgb
                delta_text = "0"
            else:
                print(f"Missing T0 baseline for well {well_number}; leaving Δcolor blank.")
                delta_text = ""
        else:
            delta_value = calculate_color_delta(baseline, rgb)
            delta_text = format_number(delta_value, DELTA_DECIMALS)

        return [
            format_number(time_min, TIME_DECIMALS),
            format_number(rgb[0], RGB_DECIMALS),
            format_number(rgb[1], RGB_DECIMALS),
            format_number(rgb[2], RGB_DECIMALS),
            delta_text,
        ]

    def append_well_block(self, row, well_number, well_block):
        row.extend(well_block)
        if int(well_number) < self.total_wells:
            row.append("")

    def write_round_row(self, row):
        with open(self.csv_path, "a", newline="", encoding="utf-8") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(row)
