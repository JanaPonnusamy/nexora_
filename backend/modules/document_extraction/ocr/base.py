"""Chunk 6 — OCR abstraction. Engine-agnostic provider interface.

Business logic must depend only on OCRProvider and ocr.models, never on a
specific engine package. paddle_engine.py is the only concrete
implementation today; adding a future engine (EasyOCR, Tesseract, Vision
AI) means writing a new OCRProvider subclass in its own module plus a
factory.py registry entry — nothing that already calls OCRFactory.create()
changes.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List

from modules.document_extraction.ocr.models import Language, OCRDocument


class OCRProvider(ABC):
    """One OCR engine, wrapped behind a uniform interface. Implementations
    own all engine-specific setup (model loading, GPU/CPU selection,
    language packs) and must normalize their raw output into OCRDocument
    before returning — see each implementation's module docstring for its
    specific normalization rules."""

    @abstractmethod
    def extract(self, page_image_paths: List[Path]) -> OCRDocument:
        """Runs OCR over one document's already-preprocessed page images,
        passed in page order (as produced by preprocessing.process_page /
        service.run_image_processing), and returns a single normalized
        OCRDocument covering all pages. Page order in the input list is
        trusted and preserved as OCRPage.page_no — this call does not
        re-derive page order itself."""
        raise NotImplementedError

    @abstractmethod
    def health_check(self) -> bool:
        """True if the engine is loaded and ready to serve extract() calls
        (models downloaded/initialized, runtime available). Intended for a
        startup/readiness probe, not called per-request."""
        raise NotImplementedError

    @abstractmethod
    def version(self) -> str:
        """Engine + model version string, recorded onto
        OCRDocument.engine_version so a stored result can be traced back to
        what produced it."""
        raise NotImplementedError

    @abstractmethod
    def supported_languages(self) -> List[Language]:
        raise NotImplementedError
