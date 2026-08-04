import cv2
import numpy as np
import logging

from util.rectangle_detection_settings import RectangleDetectionSettings

logger = logging.getLogger(__name__)


## Default values (used by RectangleDetectionSettings and backward-compatible imports)
## HIGHER values in this section means more rectangles will be detected
##----------------------------------------------------------------

blur_kernel_size = 3
dilate_iterations = 7
epsilon_factor = 0.02

## LOWER values in this section means more rectangles will be detected
##----------------------------------------------------------

canny_low_threshold = 60
canny_high_threshold = 150

## Size of the rectangles to detect, and miscellaneous settings
##----------------------------------------------------------------

overlap_threshold_value = 0.7
min_area = 500
max_area = 30000


def _resolve_settings(
    settings: RectangleDetectionSettings | None,
) -> RectangleDetectionSettings:
    if settings is None:
        return RectangleDetectionSettings.from_dict(
            {
                "blur_kernel_size": blur_kernel_size,
                "dilate_iterations": dilate_iterations,
                "epsilon_factor": epsilon_factor,
                "canny_low_threshold": canny_low_threshold,
                "canny_high_threshold": canny_high_threshold,
                "overlap_threshold_value": overlap_threshold_value,
                "min_area": min_area,
                "max_area": max_area,
            }
        )
    settings.normalize()
    return settings


def detect_rectangles_multi_method(
    image_cv,
    settings: RectangleDetectionSettings | None = None,
):
    """
    Detect rectangles using multiple methods and combine results.

    Args:
        image_cv: OpenCV image (BGR format)
        settings: Detection parameters; module defaults when None

    Returns:
        List of rectangles as tuples (x, y, width, height)
    """
    cfg = _resolve_settings(settings)
    all_rectangles = []

    gray = cv2.cvtColor(image_cv, cv2.COLOR_BGR2GRAY)
    k = cfg.blur_kernel_size
    blurred = cv2.GaussianBlur(gray, (k, k), 0)
    edges = cv2.Canny(
        blurred, cfg.canny_low_threshold, cfg.canny_high_threshold
    )

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    dilated = cv2.dilate(edges, kernel, iterations=cfg.dilate_iterations)

    contours, _ = cv2.findContours(
        dilated, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
    )

    for contour in contours:
        area = cv2.contourArea(contour)
        if area < cfg.min_area or area > cfg.max_area:
            continue

        perimeter = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, cfg.epsilon_factor * perimeter, True)

        if len(approx) == 4:
            x, y, w, h = cv2.boundingRect(approx)
            aspect_ratio = float(w) / h if h > 0 else 0
            if 0.1 < aspect_ratio < 10:
                all_rectangles.append((x, y, w, h))

    if cfg.include_adaptive_method:
        all_rectangles.extend(detect_rectangles(image_cv, settings=cfg))

    unique_rectangles = remove_duplicate_rectangles(all_rectangles, cfg)

    if cfg.auto_remove_inner:
        unique_rectangles = remove_inner_rectangles(unique_rectangles)

    logger.info(
        "Detected %d unique rectangles after deduplication",
        len(unique_rectangles),
    )
    return unique_rectangles


def detect_rectangles(
    image_cv,
    settings: RectangleDetectionSettings | None = None,
    *,
    min_area=None,
    max_area=None,
    epsilon_factor=None,
):
    """
    Detect rectangles in an image using adaptive thresholding.

    Args:
        image_cv: OpenCV image (BGR format)
        settings: Detection parameters; module defaults when None
        min_area, max_area, epsilon_factor: Deprecated overrides when settings is None

    Returns:
        List of rectangles as tuples (x, y, width, height)
    """
    cfg = _resolve_settings(settings)
    if settings is None and any(v is not None for v in (min_area, max_area, epsilon_factor)):
        cfg = RectangleDetectionSettings.from_dict(cfg.to_dict())
        if min_area is not None:
            cfg.min_area = int(min_area)
        if max_area is not None:
            cfg.max_area = int(max_area)
        if epsilon_factor is not None:
            cfg.epsilon_factor = float(epsilon_factor)
        cfg.normalize()

    rectangles = []

    gray = cv2.cvtColor(image_cv, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    thresh = cv2.adaptiveThreshold(
        blurred,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        11,
        2,
    )

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    morph = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

    contours, hierarchy = cv2.findContours(
        morph, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
    )

    logger.info("Found %d contours", len(contours))

    for contour in contours:
        area = cv2.contourArea(contour)

        if area < cfg.min_area or area > cfg.max_area:
            continue

        perimeter = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, cfg.epsilon_factor * perimeter, True)

        if len(approx) == 4:
            x, y, w, h = cv2.boundingRect(approx)
            aspect_ratio = float(w) / h if h > 0 else 0
            if 0.1 < aspect_ratio < 10:
                rectangles.append((x, y, w, h))
                logger.debug(
                    "Detected rectangle: (%s, %s, %s, %s), area=%s",
                    x,
                    y,
                    w,
                    h,
                    area,
                )

    logger.info("Detected %d rectangles", len(rectangles))
    return rectangles


def remove_duplicate_rectangles(rectangles, settings=None):
    """
    Remove duplicate rectangles based on overlap.

    Args:
        rectangles: List of rectangles as (x, y, width, height)
        settings: Detection parameters for overlap threshold

    Returns:
        List of unique rectangles
    """
    if not rectangles:
        return []

    cfg = _resolve_settings(settings)
    overlap = cfg.overlap_threshold_value

    sorted_rects = sorted(rectangles, key=lambda r: r[2] * r[3], reverse=True)
    unique = []

    for rect in sorted_rects:
        is_duplicate = False
        for unique_rect in unique:
            if calculate_iou(rect, unique_rect) > overlap:
                is_duplicate = True
                break

        if not is_duplicate:
            unique.append(rect)

    return unique


def rect_contains(outer, inner):
    """
    Return True if inner is entirely inside outer (same or strictly inside).

    Args:
        outer: Tuple (x, y, width, height)
        inner: Tuple (x, y, width, height)

    Returns:
        True if inner's bounding box is entirely within outer's.
    """
    x_o, y_o, w_o, h_o = outer
    x_i, y_i, w_i, h_i = inner
    return (
        x_i >= x_o
        and y_i >= y_o
        and (x_i + w_i) <= (x_o + w_o)
        and (y_i + h_i) <= (y_o + h_o)
    )


def remove_inner_rectangles(rectangles):
    """
    Remove rectangles that are entirely contained within another.
    When both inner and outer perimeter of the same box are detected,
    the inner one is removed.

    Args:
        rectangles: List of rectangles as (x, y, width, height)

    Returns:
        List of rectangles with inner ones removed.
    """
    if not rectangles:
        return []

    result = []
    for rect in rectangles:
        is_inner = False
        for other in rectangles:
            if other == rect:
                continue
            if rect_contains(other, rect):
                is_inner = True
                break
        if not is_inner:
            result.append(rect)
    return result


def calculate_iou(rect1, rect2):
    """
    Calculate Intersection over Union (IoU) between two rectangles.

    Args:
        rect1: Tuple (x, y, width, height)
        rect2: Tuple (x, y, width, height)

    Returns:
        IoU value (0 to 1)
    """
    x1, y1, w1, h1 = rect1
    x2, y2, w2, h2 = rect2

    x_left = max(x1, x2)
    y_top = max(y1, y2)
    x_right = min(x1 + w1, x2 + w2)
    y_bottom = min(y1 + h1, y2 + h2)

    if x_right < x_left or y_bottom < y_top:
        return 0.0

    intersection_area = (x_right - x_left) * (y_bottom - y_top)

    rect1_area = w1 * h1
    rect2_area = w2 * h2
    union_area = rect1_area + rect2_area - intersection_area

    if union_area == 0:
        return 0.0

    return intersection_area / union_area
