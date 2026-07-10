"""Invoice Parser abstraction (pre-Chunk-7). Parser selection.

Mirrors ocr/factory.py's pattern: business logic never instantiates a
parser class directly, it asks ParserFactory for one. Only GenericInvoiceParser
exists today; document-type-specific parsers (medicine invoice, credit
note, delivery challan) are named in the Development Plan as future work —
requesting one now fails with a clear "not implemented" error rather than a
generic lookup failure.
"""

from typing import Dict, Optional, Type

from modules.document_extraction.parser.base import InvoiceParser

_DEFAULT_PARSER = "generic"

_PLANNED_PARSERS = {"medicine_invoice", "credit_note", "delivery_challan"}

_instances: Dict[str, InvoiceParser] = {}


def _registry() -> Dict[str, Type[InvoiceParser]]:
    # Imported lazily so importing parser_factory.py never forces
    # generic_invoice_parser's import chain unless a parser is actually
    # requested (mirrors ocr/factory.py's reasoning).
    from modules.document_extraction.parser.generic_invoice_parser import GenericInvoiceParser

    return {"generic": GenericInvoiceParser}


class ParserFactory:
    """Returns a cached InvoiceParser instance for the requested document
    type. One instance per type per process — parsers here are stateless
    pure functions, so reuse is just an allocation saving, not a
    correctness requirement (unlike OCRFactory, where reuse avoids
    reloading model weights)."""

    @staticmethod
    def create(document_type: Optional[str] = None) -> InvoiceParser:
        name = (document_type or _DEFAULT_PARSER).strip().lower()

        if name in _instances:
            return _instances[name]

        if name in _PLANNED_PARSERS:
            raise NotImplementedError(
                f"Parser '{name}' is planned but not implemented yet. Add its "
                f"InvoiceParser in parser/ and register it in "
                f"ParserFactory._registry()."
            )

        registry = _registry()
        parser_cls = registry.get(name)
        if parser_cls is None:
            raise ValueError(
                f"Unknown parser '{name}'. Available: {sorted(registry)} "
                f"(planned: {sorted(_PLANNED_PARSERS)})"
            )

        instance = parser_cls()
        _instances[name] = instance
        return instance
