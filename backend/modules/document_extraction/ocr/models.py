"""Chunk 6 — OCR abstraction. Engine-agnostic OCR output models.

OCRDocument (and everything it's built from) is the ONLY shape any
OCR-consuming business logic — invoice parser, supplier detection, header
parser, table parser, product parser (Chunks 7-9) — may depend on. No stage
past ocr/ ever sees a raw engine response; every OCRProvider implementation
(paddle_engine.py today, others later) is responsible for normalizing its
engine's native output into these models before returning.

Distinct from json_contracts.OCRResultContract, which is the frozen
doc_import.ocr_json *storage* shape (see
docs/Document_Extraction_JSON_Contracts.md §3). That contract is a flatter
projection written when a completed OCR run is persisted; OCRDocument is
the richer in-process interchange format engines and parsers work with,
and it carries fields (tables, per-entity language/rotation, structured
confidence) that storage doesn't need.
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel


class Language(str, Enum):
    ENGLISH = "en"
    HINDI = "hi"
    TAMIL = "ta"
    UNKNOWN = "unknown"


class Rotation(int, Enum):
    NONE = 0
    ROTATE_90 = 90
    ROTATE_180 = 180
    ROTATE_270 = 270


class BoundingBox(BaseModel):
    """Axis-aligned box in source-image pixel coordinates, origin top-left.
    Always normalized (x1 <= x2, y1 <= y2, all >= 0) regardless of how the
    originating engine represents geometry (e.g. PaddleOCR's rotated
    4-point quads are reduced to their axis-aligned bounding rect during
    normalization)."""
    x1: int
    y1: int
    x2: int
    y2: int


class Confidence(BaseModel):
    """Normalized to [0.0, 1.0] regardless of the engine's native scale.
    Every OCRProvider must convert its engine's raw score (e.g. a 0-100
    percentage) into this range during normalization."""
    score: float

    def __float__(self) -> float:
        return self.score


class OCRWord(BaseModel):
    text: str
    confidence: Confidence
    bbox: BoundingBox


class OCRLine(BaseModel):
    line_no: int
    text: str
    confidence: Confidence
    bbox: BoundingBox
    words: List[OCRWord] = []


class OCRCell(BaseModel):
    row: int
    col: int
    text: str
    confidence: Confidence
    bbox: BoundingBox
    row_span: int = 1
    col_span: int = 1


class OCRTable(BaseModel):
    table_no: int
    bbox: BoundingBox
    row_count: int
    col_count: int
    cells: List[OCRCell] = []


class OCRPage(BaseModel):
    page_no: int
    width_px: int
    height_px: int
    rotation: Rotation = Rotation.NONE
    language: Language = Language.UNKNOWN
    lines: List[OCRLine] = []
    tables: List[OCRTable] = []


class OCRDocument(BaseModel):
    engine_name: str
    engine_version: Optional[str] = None
    pages: List[OCRPage] = []
    average_confidence: Optional[Confidence] = None
