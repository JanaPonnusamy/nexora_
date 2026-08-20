"""OCR value normalization at the product-table boundary."""

from modules.document_extraction.table_engine.table_understanding_engine import _to_float


def test_gst_percent_keeps_the_number_when_the_invoice_prints_a_tax_marker():
    # The supplied Nathan Medicals bill renders GST cells as `5 % G`.
    assert _to_float("5 % G") == 5.0


def test_a_cell_without_any_number_stays_missing():
    assert _to_float("GST") is None
    assert _to_float("AMLODAC 5MG") is None
