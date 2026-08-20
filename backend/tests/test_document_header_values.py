"""Invoice header normalization for common printed bill labels."""

from modules.document_extraction.parser.generic_invoice_parser import _clean_header_value


def test_bill_number_drops_the_page_counter_from_a_shared_box():
    assert _clean_header_value("invoice_number", "26-27D1312 1/1") == "26-27D1312"


def test_slashes_inside_a_real_invoice_number_are_preserved():
    assert _clean_header_value("invoice_number", "SI/26-27/4821") == "SI/26-27/4821"
