"""OCR abstraction layer (Chunk 6).

Business logic must import from here (or ocr.base / ocr.models) and never
import a specific engine package (e.g. paddleocr) directly — see base.py's
and paddle_engine.py's module docstrings for why. Get a provider via
OCRFactory.create(), call .extract() on it, and consume the returned
OCRDocument.
"""

from modules.document_extraction.ocr.base import OCRProvider
from modules.document_extraction.ocr.factory import OCRFactory
from modules.document_extraction.ocr.models import (
    BoundingBox,
    Confidence,
    Language,
    OCRCell,
    OCRDocument,
    OCRLine,
    OCRPage,
    OCRTable,
    OCRWord,
    Rotation,
)

__all__ = [
    "OCRProvider",
    "OCRFactory",
    "OCRDocument",
    "OCRPage",
    "OCRLine",
    "OCRWord",
    "OCRTable",
    "OCRCell",
    "BoundingBox",
    "Confidence",
    "Language",
    "Rotation",
]
