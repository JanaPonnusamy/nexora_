"""Chunk 6 — OCR abstraction. PaddleOCR provider.

This is the ONLY module in the codebase allowed to import paddleocr (or
paddle) — see base.py's module docstring. Everything PaddleOCRProvider
returns is a normalized OCRDocument (ocr/models.py); nothing downstream
ever sees a raw PaddleOCR result tuple.

The import is deferred to first use (_ensure_loaded), not done at module
load time, for two reasons: (1) paddlepaddle/paddleocr are large,
slow-to-import packages and other engines shouldn't pay that cost just
because this module is reachable via the factory's registry, and (2) it
lets factory.py / this module be imported (e.g. for type-checking, or by
tooling that walks the package) even in an environment where paddleocr
isn't installed yet, raising a clear error only when the engine is
actually used.

Normalization notes (raw PaddleOCR -> OCRDocument):
  * PaddleOCR's base `ocr()` pipeline is LINE-level only — it does not
    natively segment words or detect tables. OCRPage.tables is therefore
    always empty here (row/column/table grouping over lines is business
    logic — Chunk 9 — applied to OCRDocument.pages[].lines, not an OCR
    engine concern). OCRWord entries are a whitespace-split approximation
    distributed proportionally across each line's bounding box by
    character count, not natively-detected word boxes.
  * Coordinates: PaddleOCR returns a 4-point (possibly rotated) quad per
    detection; _quad_to_bbox reduces it to an axis-aligned, non-negative
    BoundingBox.
  * Confidence: PaddleOCR's rec_score is already 0-1; still explicitly
    clamped to [0, 1] and rounded so no engine can violate the Confidence
    contract.
  * Whitespace: collapsed to single spaces, stripped; empty lines dropped.
  * Merge split words: adjacent detections on the same text row with a
    small horizontal gap (a common PaddleOCR artifact near tight kerning
    or table borders splitting one visual phrase into two boxes) are
    merged into a single line before word-splitting. The gap threshold is
    intentionally tight (30% of shared row height) so genuinely separate
    table columns are not merged into one line.
  * Line order: lines are sorted top-to-bottom, then left-to-right
    (bbox.y1, then bbox.x1) and renumbered 1..N — not trusted to already
    arrive in reading order from the engine.
  * Page order: preserved as given by the caller (see base.py); this
    module does not reorder pages.
  * Orientation: PaddleOCR's angle classifier (cls=True) only corrects
    0/180 upside-down text, not 90/270 sideways pages (a common case for
    phone-photographed invoices held in portrait). After the first OCR
    pass, _looks_sideways() checks for the tell-tale sign of a rotated
    page — detected line boxes that are taller than they are wide, which
    real horizontal invoice text never produces — or a near-empty page,
    and only then retries at 90/180/270 and keeps whichever rotation
    yields the highest text-yield score (_score_raw_lines). Well-oriented
    pages (the common case) pay for exactly one OCR pass.
"""

import re
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np

from modules.document_extraction.ocr.base import OCRProvider
from modules.document_extraction.ocr.models import (
    BoundingBox,
    Confidence,
    Language,
    OCRDocument,
    OCRLine,
    OCRPage,
    OCRWord,
    Rotation,
)

_WHITESPACE_RE = re.compile(r"\s+")
_MERGE_GAP_RATIO = 0.3  # fraction of shared row height treated as "same word"

_LANG_MAP = {"en": Language.ENGLISH, "hi": Language.HINDI, "ta": Language.TAMIL}


class PaddleOCRProvider(OCRProvider):
    """Wraps paddleocr.PaddleOCR (detection + angle classification +
    recognition). One instance per language, model weights loaded lazily
    on first extract()/health_check() call and reused after that — see
    OCRFactory, which caches provider instances for this reason."""

    _ENGINE_NAME = "PaddleOCR"

    def __init__(self, lang: str = "en"):
        self._lang = lang
        self._ocr = None

    def _ensure_loaded(self):
        if self._ocr is not None:
            return
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise RuntimeError(
                "paddleocr is not installed. Install `paddleocr` and "
                "`paddlepaddle` (listed in backend/requirements.txt) before "
                "using PaddleOCRProvider."
            ) from exc
        self._ocr = PaddleOCR(use_angle_cls=True, lang=self._lang, show_log=False)

    def extract(self, page_image_paths: List[Path]) -> OCRDocument:
        self._ensure_loaded()

        pages: List[OCRPage] = []
        all_scores: List[float] = []

        for page_no, image_path in enumerate(page_image_paths, start=1):
            image = cv2.imread(str(image_path))
            if image is None:
                raise ValueError(f"Could not read image for OCR: {image_path}")

            raw_lines = self._ocr_array(image)
            rotation = Rotation.NONE

            if _looks_sideways(raw_lines):
                best_score = _score_raw_lines(raw_lines)
                for degrees in (90, 180, 270):
                    candidate_image = _rotate_image(image, degrees)
                    candidate_lines = self._ocr_array(candidate_image)
                    candidate_score = _score_raw_lines(candidate_lines)
                    if candidate_score > best_score:
                        best_score = candidate_score
                        raw_lines = candidate_lines
                        image = candidate_image
                        rotation = Rotation(degrees)

            height_px, width_px = image.shape[:2]
            lines = _normalize_lines(raw_lines)
            pages.append(OCRPage(
                page_no=page_no,
                width_px=width_px,
                height_px=height_px,
                rotation=rotation,
                language=_LANG_MAP.get(self._lang, Language.UNKNOWN),
                lines=lines,
                tables=[],
            ))
            all_scores.extend(line.confidence.score for line in lines)

        average_confidence = (
            Confidence(score=round(sum(all_scores) / len(all_scores), 4))
            if all_scores else None
        )

        return OCRDocument(
            engine_name=self._ENGINE_NAME,
            engine_version=self.version(),
            pages=pages,
            average_confidence=average_confidence,
        )

    def _ocr_array(self, image: np.ndarray) -> list:
        raw_result = self._ocr.ocr(image, cls=True)
        return (raw_result[0] if raw_result else []) or []

    def health_check(self) -> bool:
        try:
            self._ensure_loaded()
            return self._ocr is not None
        except RuntimeError:
            return False

    def version(self) -> str:
        try:
            import paddleocr
            return getattr(paddleocr, "__version__", "unknown")
        except ImportError:
            return "unknown"

    def supported_languages(self) -> List[Language]:
        return [Language.ENGLISH, Language.HINDI, Language.TAMIL]


# --------------------------------------------------------------------------
# Normalization helpers (raw PaddleOCR -> OCRLine/OCRWord)
# --------------------------------------------------------------------------

def _normalize_whitespace(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", (text or "")).strip()


# --------------------------------------------------------------------------
# Orientation retry (see module docstring "Orientation" note)
# --------------------------------------------------------------------------

_MIN_TEXT_YIELD = 20  # total recognized chars below this = treat page as unreadable
_SIDEWAYS_ASPECT_RATIO = 1.3  # bbox height/width above this (median) = likely 90/270 rotated


def _rotate_image(image: np.ndarray, degrees: int) -> np.ndarray:
    if degrees == 90:
        return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    if degrees == 180:
        return cv2.rotate(image, cv2.ROTATE_180)
    if degrees == 270:
        return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return image


def _score_raw_lines(raw_lines) -> float:
    """Text-yield score: total recognized characters weighted by
    confidence. Correct orientation reliably yields more, longer,
    higher-confidence lines than a sideways/upside-down attempt at the
    same page, so the highest-scoring rotation wins."""
    total = 0.0
    for _quad, (text, score) in raw_lines:
        text = _normalize_whitespace(text)
        total += len(text) * max(0.0, min(1.0, float(score)))
    return total


def _looks_sideways(raw_lines) -> bool:
    """True if this OCR pass looks like it hit a 90/270-rotated page —
    either almost nothing was recognized, or the detected line boxes are
    (on median) taller than they are wide, which real horizontal invoice
    text never produces. PaddleOCR's cls=True already self-corrects 0/180
    upside-down text, so this specifically catches what cls can't."""
    total_chars = 0
    ratios = []
    for quad, (text, _score) in raw_lines:
        total_chars += len(_normalize_whitespace(text))
        bbox = _quad_to_bbox(quad)
        width = bbox.x2 - bbox.x1
        height = bbox.y2 - bbox.y1
        if width > 0:
            ratios.append(height / width)
    if total_chars < _MIN_TEXT_YIELD:
        return True
    if not ratios:
        return False
    ratios.sort()
    median_ratio = ratios[len(ratios) // 2]
    return median_ratio > _SIDEWAYS_ASPECT_RATIO


def _quad_to_bbox(quad) -> BoundingBox:
    xs = [point[0] for point in quad]
    ys = [point[1] for point in quad]
    return BoundingBox(
        x1=max(0, round(min(xs))), y1=max(0, round(min(ys))),
        x2=max(0, round(max(xs))), y2=max(0, round(max(ys))),
    )


def _same_row_adjacent(a: BoundingBox, b: BoundingBox) -> bool:
    shared_height = max(min(a.y2 - a.y1, b.y2 - b.y1), 1)
    overlap = min(a.y2, b.y2) - max(a.y1, b.y1)
    if overlap < shared_height * 0.5:
        return False
    gap = b.x1 - a.x2
    return 0 <= gap < shared_height * _MERGE_GAP_RATIO


def _merge_split_words(parsed: List[Tuple[BoundingBox, str, float]]) -> List[Tuple[BoundingBox, str, float]]:
    if not parsed:
        return parsed
    parsed = sorted(parsed, key=lambda item: (item[0].y1, item[0].x1))
    merged = [parsed[0]]
    for bbox, text, score in parsed[1:]:
        prev_bbox, prev_text, prev_score = merged[-1]
        if _same_row_adjacent(prev_bbox, bbox):
            merged[-1] = (
                BoundingBox(
                    x1=min(prev_bbox.x1, bbox.x1), y1=min(prev_bbox.y1, bbox.y1),
                    x2=max(prev_bbox.x2, bbox.x2), y2=max(prev_bbox.y2, bbox.y2),
                ),
                f"{prev_text} {text}".strip(),
                (prev_score + score) / 2,
            )
        else:
            merged.append((bbox, text, score))
    return merged


def _split_words(text: str, line_bbox: BoundingBox, line_confidence: Confidence) -> List[OCRWord]:
    """Approximates per-word boxes by distributing the line bbox width
    across whitespace-split tokens, proportional to token character count.
    PaddleOCR's base pipeline has no native word segmentation to draw on."""
    tokens = [t for t in text.split(" ") if t]
    if not tokens:
        return []
    total_chars = sum(len(t) for t in tokens) or 1
    line_width = max(line_bbox.x2 - line_bbox.x1, 1)
    words = []
    cursor = line_bbox.x1
    for token in tokens:
        token_width = max(round(line_width * (len(token) / total_chars)), 1)
        word_bbox = BoundingBox(
            x1=cursor, y1=line_bbox.y1,
            x2=min(cursor + token_width, line_bbox.x2), y2=line_bbox.y2,
        )
        words.append(OCRWord(text=token, confidence=line_confidence, bbox=word_bbox))
        cursor += token_width
    return words


def _normalize_lines(raw_lines) -> List[OCRLine]:
    parsed: List[Tuple[BoundingBox, str, float]] = []
    for quad, (text, score) in raw_lines:
        text = _normalize_whitespace(text)
        if not text:
            continue
        parsed.append((_quad_to_bbox(quad), text, max(0.0, min(1.0, float(score)))))

    parsed = _merge_split_words(parsed)
    parsed.sort(key=lambda item: (item[0].y1, item[0].x1))

    lines: List[OCRLine] = []
    for line_no, (bbox, text, score) in enumerate(parsed, start=1):
        confidence = Confidence(score=round(score, 4))
        lines.append(OCRLine(
            line_no=line_no, text=text, confidence=confidence,
            bbox=bbox, words=_split_words(text, bbox, confidence),
        ))
    return lines
