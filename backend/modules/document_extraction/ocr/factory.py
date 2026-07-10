"""Chunk 6 — OCR abstraction. Engine selection.

The only place that decides which concrete OCRProvider business logic
gets. Reads the engine name from config (env var OCR_ENGINE, default
"paddleocr") so swapping engines is a config change, never a code change
in any caller — callers always do `OCRFactory.create()` and get back an
OCRProvider, never a specific engine class.
"""

import os
from typing import Dict, Optional, Type

from modules.document_extraction.ocr.base import OCRProvider

_ENGINE_ENV_VAR = "OCR_ENGINE"
_DEFAULT_ENGINE = "paddleocr"

# Named in the Development Plan as future engines; not implemented yet.
# Listed explicitly so requesting one fails with a clear "not implemented"
# message instead of a generic "unknown engine" one.
_PLANNED_ENGINES = {"easyocr", "tesseract", "visionai"}

_instances: Dict[str, OCRProvider] = {}


def _registry() -> Dict[str, Type[OCRProvider]]:
    # Imported lazily, inside the function, so that importing factory.py
    # (or the ocr package) never forces paddle_engine's import chain —
    # and therefore never requires paddleocr to be installed — unless an
    # engine is actually requested.
    from modules.document_extraction.ocr.paddle_engine import PaddleOCRProvider

    return {"paddleocr": PaddleOCRProvider}


class OCRFactory:
    """Returns a cached OCRProvider instance for the configured engine. One
    instance per engine name per process — engines like PaddleOCR are
    expensive to initialize (model load) and are safe to reuse across
    requests."""

    @staticmethod
    def create(engine_name: Optional[str] = None) -> OCRProvider:
        name = (engine_name or os.environ.get(_ENGINE_ENV_VAR, _DEFAULT_ENGINE)).strip().lower()

        if name in _instances:
            return _instances[name]

        if name in _PLANNED_ENGINES:
            raise NotImplementedError(
                f"OCR engine '{name}' is planned but not implemented yet. "
                f"Add its OCRProvider in ocr/ and register it in "
                f"OCRFactory._registry()."
            )

        registry = _registry()
        provider_cls = registry.get(name)
        if provider_cls is None:
            raise ValueError(
                f"Unknown OCR engine '{name}'. Available: {sorted(registry)} "
                f"(planned: {sorted(_PLANNED_ENGINES)})"
            )

        instance = provider_cls()
        _instances[name] = instance
        return instance
