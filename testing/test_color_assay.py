import csv
import os
import sys
import uuid

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import module_color_assay as MCA


class FakeCV2:
    IMREAD_UNCHANGED = -1

    @staticmethod
    def imwrite(path, image):
        with open(path, "wb") as image_file:
            np.save(image_file, image)
        return True

    @staticmethod
    def imread(path, flags=None):
        try:
            with open(path, "rb") as image_file:
                return np.load(image_file, allow_pickle=False)
        except FileNotFoundError:
            return None


MCA.cv2 = FakeCV2


CAPTURE_STATE = {
    "preview_size": (100, 100),
    "radius": 20,
    "line_thickness": 1,
}
TEMP_PARENT_DIR = os.path.dirname(__file__)


def assert_rgb_close(actual_rgb, expected_rgb, tolerance=1e-6):
    for actual, expected in zip(actual_rgb, expected_rgb):
        assert abs(actual - expected) <= tolerance, f"expected {expected_rgb}, got {actual_rgb}"


def build_center_roi_image(rgb):
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    bgr = (rgb[2], rgb[1], rgb[0])
    image[31:69, 31:69] = bgr
    return image


def build_alpha_masked_outlier_image(base_rgb, dark_rgb, bright_rgb):
    image = np.zeros((2, 5, 4), dtype=np.uint8)
    base_bgr = (base_rgb[2], base_rgb[1], base_rgb[0], 255)
    dark_bgr = (dark_rgb[2], dark_rgb[1], dark_rgb[0], 255)
    bright_bgr = (bright_rgb[2], bright_rgb[1], bright_rgb[0], 255)
    image[:, :] = base_bgr
    image[0, 0] = dark_bgr
    image[0, 1] = bright_bgr
    return image


def write_image(path, image):
    ok = MCA.cv2.imwrite(path, image)
    assert ok, f"failed to write image: {path}"


def build_test_path(label, extension):
    return os.path.join(TEMP_PARENT_DIR, f"color_assay_test_{label}_{uuid.uuid4().hex}{extension}")


def cleanup_paths(*paths):
    for path in paths:
        if path and os.path.exists(path):
            os.remove(path)


def test_measure_mean_rgb_from_circle_roi():
    image_path = build_test_path("full_frame", ".png")
    try:
        write_image(image_path, build_center_roi_image((10, 20, 30)))
        rgb = MCA.measure_mean_rgb(image_path, capture_state=CAPTURE_STATE, trim_percent=0)
        assert_rgb_close(rgb, (10.0, 20.0, 30.0))
    finally:
        cleanup_paths(image_path)


def test_measure_mean_rgb_from_alpha_mask():
    image_path = build_test_path("cropped_roi", ".png")
    try:
        image = np.zeros((4, 4, 4), dtype=np.uint8)
        image[1, 1] = (30, 20, 10, 255)
        image[1, 2] = (60, 50, 40, 255)
        image[0, 0] = (255, 255, 255, 0)
        write_image(image_path, image)
        rgb = MCA.measure_mean_rgb(image_path, trim_percent=0)
        assert_rgb_close(rgb, (25.0, 35.0, 45.0))
    finally:
        cleanup_paths(image_path)


def test_zero_trim_matches_plain_mean_with_outliers():
    image_path = build_test_path("outliers_untrimmed", ".png")
    try:
        image = build_alpha_masked_outlier_image(
            base_rgb=(100, 110, 120),
            dark_rgb=(0, 0, 0),
            bright_rgb=(255, 255, 255),
        )
        write_image(image_path, image)
        rgb = MCA.measure_mean_rgb(image_path, trim_percent=0)
        assert_rgb_close(rgb, (105.5, 113.5, 121.5))
    finally:
        cleanup_paths(image_path)


def test_trimmed_mean_resists_extreme_pixels():
    image_path = build_test_path("outliers_trimmed", ".png")
    try:
        image = build_alpha_masked_outlier_image(
            base_rgb=(100, 110, 120),
            dark_rgb=(0, 0, 0),
            bright_rgb=(255, 255, 255),
        )
        write_image(image_path, image)
        rgb = MCA.measure_mean_rgb(image_path, trim_percent=10)
        assert_rgb_close(rgb, (100.0, 110.0, 120.0))
    finally:
        cleanup_paths(image_path)


def test_color_delta_math():
    delta = MCA.calculate_color_delta((0.0, 0.0, 0.0), (3.0, 4.0, 0.0))
    assert abs(delta - 5.0) <= 1e-9, f"expected 5.0, got {delta}"


def test_per_well_baselines_stay_isolated():
    temp_files = []
    csv_path = build_test_path("baselines", ".csv")
    try:
        tracker = MCA.ColorAssayTracker(
            save_folder=TEMP_PARENT_DIR,
            total_wells=2,
            csv_path=csv_path,
            trim_percent=0,
        )

        paths = {}
        image_specs = {
            "w1_t0": (0, 0, 0),
            "w1_t1": (3, 4, 0),
            "w2_t0": (10, 10, 10),
            "w2_t1": (13, 10, 10),
        }
        for key, rgb in image_specs.items():
            image_path = build_test_path(key, ".png")
            write_image(image_path, build_center_roi_image(rgb))
            paths[key] = image_path
            temp_files.append(image_path)

        block_w1_t0 = tracker.build_well_block(1, 0, paths["w1_t0"], capture_state=CAPTURE_STATE, current_round=1)
        block_w2_t0 = tracker.build_well_block(2, 0, paths["w2_t0"], capture_state=CAPTURE_STATE, current_round=1)
        block_w1_t1 = tracker.build_well_block(1, 5, paths["w1_t1"], capture_state=CAPTURE_STATE, current_round=2)
        block_w2_t1 = tracker.build_well_block(2, 5, paths["w2_t1"], capture_state=CAPTURE_STATE, current_round=2)

        assert block_w1_t0[-1] == "0", f"unexpected T0 delta for well 1: {block_w1_t0[-1]}"
        assert block_w2_t0[-1] == "0", f"unexpected T0 delta for well 2: {block_w2_t0[-1]}"
        assert block_w1_t1[-1] == "5", f"unexpected round-2 delta for well 1: {block_w1_t1[-1]}"
        assert block_w2_t1[-1] == "3", f"unexpected round-2 delta for well 2: {block_w2_t1[-1]}"
    finally:
        cleanup_paths(csv_path, *temp_files)


def test_color_assay_csv_layout_and_failure_blanks():
    csv_path = build_test_path("layout", ".csv")
    well_1_t0_path = build_test_path("well_1_t0", ".png")
    well_2_t0_path = build_test_path("well_2_t0", ".png")
    well_2_t1_path = build_test_path("well_2_t1", ".png")
    missing_path = None
    try:
        tracker = MCA.ColorAssayTracker(
            save_folder=TEMP_PARENT_DIR,
            total_wells=2,
            csv_path=csv_path,
            trim_percent=0,
        )

        write_image(well_1_t0_path, build_center_roi_image((10, 20, 30)))
        write_image(well_2_t0_path, build_center_roi_image((40, 50, 60)))
        write_image(well_2_t1_path, build_center_roi_image((43, 54, 60)))

        round_1_row = []
        tracker.append_well_block(
            round_1_row,
            1,
            tracker.build_well_block(1, 0, well_1_t0_path, capture_state=CAPTURE_STATE, current_round=1),
        )
        tracker.append_well_block(
            round_1_row,
            2,
            tracker.build_well_block(2, 0, well_2_t0_path, capture_state=CAPTURE_STATE, current_round=1),
        )
        tracker.write_round_row(round_1_row)

        round_2_row = []
        missing_path = build_test_path("missing", ".png")
        tracker.append_well_block(
            round_2_row,
            1,
            tracker.build_well_block(1, 5, missing_path, capture_state=CAPTURE_STATE, current_round=2),
        )
        tracker.append_well_block(
            round_2_row,
            2,
            tracker.build_well_block(2, 5, well_2_t1_path, capture_state=CAPTURE_STATE, current_round=2),
        )
        tracker.write_round_row(round_2_row)

        with open(csv_path, newline="", encoding="utf-8") as csv_file:
            rows = list(csv.reader(csv_file))

        assert rows[0] == ["Well 1", "", "", "", "", "", "Well 2", "", "", "", ""], rows[0]
        assert rows[1] == ["Time (min)", "R", "G", "B", "Δcolor", "", "Time (min)", "R", "G", "B", "Δcolor"], rows[1]
        assert rows[2][0] == "0", rows[2]
        assert rows[2][6] == "0", rows[2]
        assert rows[3][0:5] == ["", "", "", "", ""], rows[3]
        assert rows[3][6] == "5", rows[3]
        assert rows[3][10] == "5", rows[3]
    finally:
        cleanup_paths(csv_path, well_1_t0_path, well_2_t0_path, well_2_t1_path, missing_path)


def main():
    tests = [
        test_measure_mean_rgb_from_circle_roi,
        test_measure_mean_rgb_from_alpha_mask,
        test_zero_trim_matches_plain_mean_with_outliers,
        test_trimmed_mean_resists_extreme_pixels,
        test_color_delta_math,
        test_per_well_baselines_stay_isolated,
        test_color_assay_csv_layout_and_failure_blanks,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")


if __name__ == "__main__":
    main()
