import cv2
import numpy as np
import logging

logger = logging.getLogger(__name__)


def detect_rectangles_multi_method(image_cv, min_area=500, max_area=50000):
    """
    Detect rectangles using multiple methods and combine results.
    
    Args:
        image_cv: OpenCV image (BGR format)
        min_area: Minimum contour area to consider
        max_area: Maximum contour area to consider
    
    Returns:
        List of rectangles as tuples (x, y, width, height)
    """
    all_rectangles = []
    
    # Method 1: Standard edge detection with Canny
    gray = cv2.cvtColor(image_cv, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    
    # Dilate edges to connect nearby contours
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    dilated = cv2.dilate(edges, kernel, iterations=2)
    
    contours, _ = cv2.findContours(dilated, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < min_area or area > max_area:
            continue
        
        perimeter = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        
        if len(approx) == 4:
            x, y, w, h = cv2.boundingRect(approx)
            aspect_ratio = float(w) / h if h > 0 else 0
            if 0.1 < aspect_ratio < 10:
                all_rectangles.append((x, y, w, h))
    
    # Method 2: Adaptive thresholding (from detect_rectangles)
    all_rectangles.extend(detect_rectangles(image_cv, min_area, max_area))
    
    # Remove duplicates (rectangles that are very close to each other)
    unique_rectangles = remove_duplicate_rectangles(all_rectangles)
    
    logger.info(f"Detected {len(unique_rectangles)} unique rectangles after deduplication")
    return unique_rectangles


def detect_rectangles(image_cv, min_area=500, max_area=50000, epsilon_factor=0.02):
    """
    Detect rectangles in an image using adaptive thresholding.
    
    Args:
        image_cv: OpenCV image (BGR format)
        min_area: Minimum contour area to consider
        max_area: Maximum contour area to consider
        epsilon_factor: Approximation accuracy factor for contour simplification
    
    Returns:
        List of rectangles as tuples (x, y, width, height)
    """
    rectangles = []
    
    # Convert to grayscale
    gray = cv2.cvtColor(image_cv, cv2.COLOR_BGR2GRAY)
    
    # Apply Gaussian blur to reduce noise
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    
    # Apply adaptive thresholding
    thresh = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
        cv2.THRESH_BINARY_INV, 11, 2
    )
    
    # Apply morphological operations to clean up
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    morph = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    
    # Find contours
    contours, hierarchy = cv2.findContours(
        morph, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
    )
    
    logger.info(f"Found {len(contours)} contours")
    
    # Process each contour
    for contour in contours:
        area = cv2.contourArea(contour)
        
        if area < min_area or area > max_area:
            continue
        
        perimeter = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, epsilon_factor * perimeter, True)
        
        if len(approx) == 4:
            x, y, w, h = cv2.boundingRect(approx)
            aspect_ratio = float(w) / h if h > 0 else 0
            if 0.1 < aspect_ratio < 10:
                rectangles.append((x, y, w, h))
                logger.debug(f"Detected rectangle: ({x}, {y}, {w}, {h}), area={area}")
    
    logger.info(f"Detected {len(rectangles)} rectangles")
    return rectangles


def remove_duplicate_rectangles(rectangles, overlap_threshold=0.7):
    """
    Remove duplicate rectangles based on overlap.
    
    Args:
        rectangles: List of rectangles as (x, y, width, height)
        overlap_threshold: IoU threshold for considering rectangles as duplicates
    
    Returns:
        List of unique rectangles
    """
    if not rectangles:
        return []
    
    # Sort by area (largest first)
    sorted_rects = sorted(rectangles, key=lambda r: r[2] * r[3], reverse=True)
    unique = []
    
    for rect in sorted_rects:
        is_duplicate = False
        for unique_rect in unique:
            if calculate_iou(rect, unique_rect) > overlap_threshold:
                is_duplicate = True
                break
        
        if not is_duplicate:
            unique.append(rect)
    
    return unique


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
    
    # Calculate intersection
    x_left = max(x1, x2)
    y_top = max(y1, y2)
    x_right = min(x1 + w1, x2 + w2)
    y_bottom = min(y1 + h1, y2 + h2)
    
    if x_right < x_left or y_bottom < y_top:
        return 0.0
    
    intersection_area = (x_right - x_left) * (y_bottom - y_top)
    
    # Calculate union
    rect1_area = w1 * h1
    rect2_area = w2 * h2
    union_area = rect1_area + rect2_area - intersection_area
    
    if union_area == 0:
        return 0.0
    
    return intersection_area / union_area

