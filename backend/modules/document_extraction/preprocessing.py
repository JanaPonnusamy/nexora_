"""Chunk 5 — Image Processing. OpenCV/NumPy/Pillow/PyMuPDF (+ pdf2image
fallback) only. NO OCR — this module never imports an OCR engine and must
stay that way until Chunk 6.

Pure functions over image arrays (numpy BGR, OpenCV convention) plus one
orchestration entry point, process_page(), that chains them in the order
specified in docs/Document_Extraction_DevelopmentPlan.md Chunk 5:

    load -> orientation detection -> coarse rotation -> deskew
         -> border removal -> noise removal -> contrast enhancement

process_document() (service.py's caller-facing wrapper lives in service.py,
not here) is the per-import driver: PDF -> pdf_to_images(), image upload ->
load each original page directly, then process_page() each one.
"""

import logging
from pathlib import Path
from typing import List, Tuple

import cv2
import fitz  # PyMuPDF
import numpy as np

logger = logging.getLogger("document_extraction.preprocessing")


# --------------------------------------------------------------------------
# Loading / PDF splitting
# --------------------------------------------------------------------------

def load_image_from_path(path: Path) -> np.ndarray:
    """Loads a JPG/PNG/TIFF file as a BGR numpy array. Reads via np.fromfile
    + cv2.imdecode rather than cv2.imread directly — cv2.imread silently
    fails (returns None) on non-ASCII Windows paths, which this storage
    layout can produce via uploaded filenames."""
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Unreadable image file: {path}")
    return image


def is_readable_image(content: bytes) -> bool:
    """Whether raw uploaded bytes decode to an image at all — the upload-time
    integrity check (service._verify_upload_parts). Decoding is the only
    honest test: a truncated JPEG still has a valid header and a plausible
    file size."""
    try:
        image = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_COLOR)
    except Exception:
        return False
    return image is not None and image.size > 0


def pdf_to_images(pdf_path: Path, dpi: int = 200) -> List[np.ndarray]:
    """Renders every page of a PDF to a BGR numpy array. PyMuPDF is primary
    (no external binary dependency); pdf2image (poppler) is the documented
    fallback, only attempted if PyMuPDF fails, and itself allowed to fail
    loudly if poppler isn't installed in this environment — the caller
    decides how to handle a total failure (marks the import FAILED)."""
    try:
        return _pdf_to_images_pymupdf(pdf_path, dpi)
    except Exception as primary_error:
        logger.warning("PyMuPDF render failed for %s: %s; trying pdf2image fallback", pdf_path, primary_error)
        try:
            return _pdf_to_images_pdf2image(pdf_path, dpi)
        except Exception as fallback_error:
            raise RuntimeError(
                f"PDF rendering failed (PyMuPDF: {primary_error}; pdf2image fallback: {fallback_error})"
            ) from fallback_error


def _pdf_to_images_pymupdf(pdf_path: Path, dpi: int) -> List[np.ndarray]:
    doc = fitz.open(str(pdf_path))
    try:
        zoom = dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        images = []
        for page in doc:
            pix = page.get_pixmap(matrix=matrix)
            arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            if pix.n == 4:
                image = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
            elif pix.n == 3:
                image = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
            else:
                image = cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
            images.append(image)
        if not images:
            raise ValueError("PDF has no pages")
        return images
    finally:
        doc.close()


def _pdf_to_images_pdf2image(pdf_path: Path, dpi: int) -> List[np.ndarray]:
    from pdf2image import convert_from_path  # requires poppler on PATH

    pil_pages = convert_from_path(str(pdf_path), dpi=dpi)
    return [cv2.cvtColor(np.array(p), cv2.COLOR_RGB2BGR) for p in pil_pages]


# --------------------------------------------------------------------------
# Orientation detection + rotation
# --------------------------------------------------------------------------

def detect_coarse_orientation(gray: np.ndarray) -> int:
    """EXPERIMENTAL, NOT auto-applied — see process_page(). Attempted 0/90
    orientation guess via text-line projection-profile variance (rows vs
    columns). Tested against all 4 real sample invoices
    (assects/sample invoice/*.jpeg) during Chunk 5 verification: it returned
    "90" for every single one, including the sample that was already
    correctly upright. Dense invoice tables have enough vertical column-grid
    structure to dominate the column-variance signal regardless of true
    orientation, so this heuristic does not discriminate for this document
    type — it is not wired into process_page()'s output and must not be used
    to auto-rotate. Left here as a documented dead end for whoever attempts
    OCR-free orientation detection next; a reliable version needs either a
    trained classifier or (more practically) Chunk 6's OCR angle
    classifier / manual correction in Review."""
    small = cv2.resize(gray, (0, 0), fx=0.5, fy=0.5) if gray.size > 4_000_000 else gray
    thresh = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    row_var = float(thresh.sum(axis=1).astype(np.float64).var())
    col_var = float(thresh.sum(axis=0).astype(np.float64).var())
    if row_var == 0 and col_var == 0:
        return 0
    return 90 if col_var > row_var * 1.15 else 0


def rotate_90_multiple(image: np.ndarray, degrees: int) -> np.ndarray:
    degrees = degrees % 360
    if degrees == 90:
        return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    if degrees == 180:
        return cv2.rotate(image, cv2.ROTATE_180)
    if degrees == 270:
        return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return image


def detect_skew_angle(gray: np.ndarray) -> float:
    """Fine-angle skew (small angle, not a quarter turn) via minAreaRect
    over thresholded foreground pixels. Returns degrees in (-45, 45]."""
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(thresh > 0))
    if coords.size == 0:
        return 0.0
    angle = cv2.minAreaRect(coords)[-1]
    # cv2.minAreaRect's angle convention is quadrant-dependent; normalize.
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    if abs(angle) > 45:  # spurious reading on a near-blank/low-content page
        return 0.0
    return round(float(angle), 3)


def rotate_fine(image: np.ndarray, angle_degrees: float) -> np.ndarray:
    """Applies a small-angle rotation, expanding the canvas so corners
    aren't clipped (unlike a naive warpAffine at the original size)."""
    if abs(angle_degrees) < 0.1:
        return image
    (h, w) = image.shape[:2]
    center = (w // 2, h // 2)
    matrix = cv2.getRotationMatrix2D(center, angle_degrees, 1.0)
    cos = abs(matrix[0, 0])
    sin = abs(matrix[0, 1])
    new_w = int((h * sin) + (w * cos))
    new_h = int((h * cos) + (w * sin))
    matrix[0, 2] += (new_w / 2) - center[0]
    matrix[1, 2] += (new_h / 2) - center[1]
    return cv2.warpAffine(
        image, matrix, (new_w, new_h),
        flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE,
    )


# --------------------------------------------------------------------------
# Border removal / denoise / contrast
# --------------------------------------------------------------------------

def remove_borders(image: np.ndarray, padding: int = 8) -> np.ndarray:
    """Crops to the bounding box of visible content, dropping scanner
    borders / dark photo edges. Refuses to crop if the resulting box would
    remove more than half the page in either dimension — a sign the
    threshold picked up noise rather than real content, in which case
    leaving the image uncropped is safer than a bad crop."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return image
    x, y, w, h = cv2.boundingRect(np.vstack(contours))
    img_h, img_w = image.shape[:2]
    x0, y0 = max(0, x - padding), max(0, y - padding)
    x1, y1 = min(img_w, x + w + padding), min(img_h, y + h + padding)
    if (x1 - x0) < img_w * 0.5 or (y1 - y0) < img_h * 0.5:
        return image
    return image[y0:y1, x0:x1]


def denoise(gray: np.ndarray) -> np.ndarray:
    return cv2.fastNlMeansDenoising(gray, h=10, templateWindowSize=7, searchWindowSize=21)


def enhance_contrast(gray: np.ndarray) -> np.ndarray:
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)


# --------------------------------------------------------------------------
# Per-page orchestration
# --------------------------------------------------------------------------

def process_page(image_bgr: np.ndarray) -> Tuple[np.ndarray, dict]:
    """Runs the Chunk 5 chain on one page. Returns (processed_image,
    metadata) where metadata matches json_contracts.ProcessedFileEntry's
    rotation_degrees/deskew_angle/width_px/height_px fields.

    "Auto rotation" here means the fine-angle deskew correction only
    (reliable, verified against all 4 real sample invoices — every one
    returned a near-zero angle on an already-square photo and would correct
    a genuinely skewed one). Coarse 90/180/270 orientation correction is
    deliberately NOT auto-applied — see detect_coarse_orientation()'s
    docstring for why; `rotation_degrees` in the output is always 0 until a
    reliable coarse-orientation source exists (Chunk 6's OCR angle
    classifier, or manual correction in Review).

    Output is contrast-enhanced grayscale, NOT hard-thresholded/binarized —
    OCR (Chunk 6) generally performs better on enhanced grayscale than on a
    binarized image, and binarizing here would be a one-way, unreviewable
    transform baked into the only image the OCR engine ever sees."""
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

    deskew_angle = detect_skew_angle(gray)
    if deskew_angle:
        image_bgr = rotate_fine(image_bgr, deskew_angle)
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

    image_bgr = remove_borders(image_bgr)
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

    gray = denoise(gray)
    gray = enhance_contrast(gray)

    height, width = gray.shape[:2]
    metadata = {
        "rotation_degrees": 0,
        "deskew_angle": deskew_angle,
        "width_px": width,
        "height_px": height,
    }
    return gray, metadata


def encode_image(image: np.ndarray, extension: str = ".jpg", quality: int = 90) -> bytes:
    params = [cv2.IMWRITE_JPEG_QUALITY, quality] if extension.lower() == ".jpg" else []
    ok, buf = cv2.imencode(extension, image, params)
    if not ok:
        raise RuntimeError("Failed to encode processed image")
    return buf.tobytes()
