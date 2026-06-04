import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from module_well_location_helper import crop_image_to_crosshair_circle


def build_test_image(width, height):
    x_channel = np.tile(np.arange(width, dtype=np.uint8), (height, 1))
    y_channel = np.tile(np.arange(height, dtype=np.uint8).reshape(height, 1), (1, width))
    red_channel = np.full((height, width), 127, dtype=np.uint8)
    return np.dstack((x_channel, y_channel, red_channel))


def test_scaled_output_size():
    image = build_test_image(300, 200)
    cropped = crop_image_to_crosshair_circle(image, preview_size=(100, 100), radius=20)
    assert cropped.shape == (80, 80, 4), f"unexpected cropped shape: {cropped.shape}"


def test_transparent_corners():
    image = build_test_image(200, 200)
    cropped = crop_image_to_crosshair_circle(image, preview_size=(100, 100), radius=25)
    alpha = cropped[..., 3]
    assert alpha[0, 0] == 0, "top-left corner should be transparent"
    assert alpha[0, -1] == 0, "top-right corner should be transparent"
    assert alpha[-1, 0] == 0, "bottom-left corner should be transparent"
    assert alpha[-1, -1] == 0, "bottom-right corner should be transparent"
    assert alpha[cropped.shape[0] // 2, cropped.shape[1] // 2] == 255, "circle center should be opaque"


def test_radius_clamping():
    image = build_test_image(60, 60)
    cropped = crop_image_to_crosshair_circle(image, preview_size=(100, 100), radius=80)
    assert cropped.shape == (60, 60, 4), f"clamped crop should fill the image, got {cropped.shape}"


def test_aspect_ratio_min_scale():
    image = build_test_image(400, 200)
    cropped = crop_image_to_crosshair_circle(image, preview_size=(100, 100), radius=20)
    assert cropped.shape == (80, 80, 4), f"expected min-scale diameter of 80, got {cropped.shape}"


def main():
    tests = [
        test_scaled_output_size,
        test_transparent_corners,
        test_radius_clamping,
        test_aspect_ratio_min_scale,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")


if __name__ == "__main__":
    main()
