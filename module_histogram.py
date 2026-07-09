"""
Live RGB histogram helpers for camera exposure tuning.
"""
from __future__ import annotations

try:
    import cv2
except ImportError:
    cv2 = None

try:
    import numpy as np
except ImportError:
    np = None

DEFAULT_BINS = 256
DEFAULT_WIDTH = 280
DEFAULT_HEIGHT = 120
CLIP_THRESHOLD = 254
CLIP_WARNING_PERCENT = 1.0

CHANNEL_COLORS_BGR = (
    (255, 0, 0),    # Blue
    (0, 255, 0),    # Green
    (0, 0, 255),    # Red
)


def _require_numpy():
    if np is None:
        raise RuntimeError("numpy is required for histogram rendering.")


def _require_cv2():
    if cv2 is None:
        raise RuntimeError("OpenCV (cv2) is required for histogram rendering.")


def compute_rgb_histograms(bgr_pixels, bins=DEFAULT_BINS):
    """
    Compute normalized RGB histograms from a 1D or 2D BGR pixel array.

    Returns a tuple of three float arrays (blue, green, red), each length `bins`.
    """
    _require_numpy()
    _require_cv2()

    pixels = np.asarray(bgr_pixels, dtype=np.uint8)
    if pixels.size == 0:
        return tuple(np.zeros(bins, dtype=np.float32) for _ in range(3))

    if pixels.ndim == 1:
        pixels = pixels.reshape(-1, 3)
    elif pixels.ndim != 2 or pixels.shape[1] != 3:
        raise ValueError("bgr_pixels must be Nx3 BGR values.")

    histograms = []
    for channel_index in range(3):
        channel_values = pixels[:, channel_index]
        hist = cv2.calcHist([channel_values], [0], None, [bins], [0, 256])
        hist = hist.reshape(-1).astype(np.float32)
        peak = float(hist.max()) if hist.size else 0.0
        if peak > 0:
            hist /= peak
        histograms.append(hist)
    return tuple(histograms)


def compute_highlight_clip_percent(bgr_pixels, threshold=CLIP_THRESHOLD):
    """
    Return per-channel highlight clip percentages for B, G, R.
    """
    _require_numpy()

    pixels = np.asarray(bgr_pixels, dtype=np.uint8)
    if pixels.size == 0:
        return (0.0, 0.0, 0.0)

    if pixels.ndim == 1:
        pixels = pixels.reshape(-1, 3)
    elif pixels.ndim != 2 or pixels.shape[1] != 3:
        raise ValueError("bgr_pixels must be Nx3 BGR values.")

    total = float(pixels.shape[0])
    clip_counts = []
    for channel_index in range(3):
        clipped = np.count_nonzero(pixels[:, channel_index] >= threshold)
        clip_counts.append((clipped / total) * 100.0)
    return tuple(clip_counts)


def format_clip_status(clip_percentages):
    blue_pct, green_pct, red_pct = clip_percentages
    return f"Highlight clip: R {red_pct:.1f}% | G {green_pct:.1f}% | B {blue_pct:.1f}%"


def clip_status_exceeds_warning(clip_percentages, warning_percent=CLIP_WARNING_PERCENT):
    return any(value > warning_percent for value in clip_percentages)


def render_histogram_image(histograms, width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT, has_clip=False):
    """
    Render overlaid B/G/R histogram curves to a BGR image.
    """
    _require_numpy()
    _require_cv2()

    if len(histograms) != 3:
        raise ValueError("histograms must contain exactly three channel arrays.")

    bins = len(histograms[0])
    plot_width = max(width - 1, 1)
    plot_height = max(height - 20, 1)
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:] = (24, 24, 24)

    if has_clip:
        image[:, max(width - 8, 0):] = (40, 40, 80)

    for channel_index, hist in enumerate(histograms):
        hist_array = np.asarray(hist, dtype=np.float32).reshape(-1)
        if hist_array.size != bins:
            raise ValueError("All channel histograms must have the same bin count.")

        points = []
        for bin_index, value in enumerate(hist_array):
            x = int(round((bin_index / max(bins - 1, 1)) * plot_width))
            y = height - 10 - int(round(float(value) * plot_height))
            points.append((x, y))

        if len(points) >= 2:
            cv2.polylines(
                image,
                [np.asarray(points, dtype=np.int32)],
                isClosed=False,
                color=CHANNEL_COLORS_BGR[channel_index],
                thickness=1,
                lineType=cv2.LINE_AA,
            )

    marker_x = int(round((255 / max(bins - 1, 1)) * plot_width))
    cv2.line(image, (marker_x, 0), (marker_x, height - 1), (180, 180, 180), 1, lineType=cv2.LINE_AA)
    cv2.putText(
        image,
        "255",
        (max(marker_x - 14, 0), height - 2),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.35,
        (200, 200, 200),
        1,
        lineType=cv2.LINE_AA,
    )
    return image


def frame_to_histogram_png(bgr_pixels, width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT, threshold=CLIP_THRESHOLD):
    """
    Build histogram PNG bytes suitable for sg.Image.update(data=...).
    """
    _require_cv2()

    histograms = compute_rgb_histograms(bgr_pixels)
    clip_percentages = compute_highlight_clip_percent(bgr_pixels, threshold=threshold)
    has_clip = clip_status_exceeds_warning(clip_percentages, warning_percent=0.0)
    image = render_histogram_image(histograms, width=width, height=height, has_clip=has_clip)
    success, encoded = cv2.imencode(".png", image)
    if not success:
        raise RuntimeError("Failed to encode histogram image.")
    return encoded.tobytes(), clip_percentages
