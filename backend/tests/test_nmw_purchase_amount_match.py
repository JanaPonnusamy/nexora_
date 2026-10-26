"""NMW Sales Report purchase entry: amount match against the store's GRN."""
from modules.nmw_sales_report.repository import _pick_amount_grn


def test_transfer_matches_grn_on_gross_amount_when_ptr_differs():
    # TO002001432: NMW purchase-price total 13019.82, header GrossAmount
    # 11821.93; NMC booked GRN 1440 at the transfer value.
    grns = [(1439, 2662.82, None), (1440, 11821.93, None), (1441, 4667.74, None)]
    assert _pick_amount_grn(grns, [13019.82]) is None
    assert _pick_amount_grn(grns, [13019.82, 11821.93])[0] == 1440


def test_no_match_outside_tolerance():
    # TO002001431: bill 3234.87, nearest GRN 2662.82 (short received).
    assert _pick_amount_grn([(1439, 2662.82, None)], [3234.87]) is None


def test_near_tie_is_not_guessed():
    grns = [(10, 1000.40, None), (11, 999.60, None)]
    assert _pick_amount_grn(grns, [1000.0]) is None


def test_exact_match_wins_even_with_a_close_neighbour():
    grns = [(10, 1000.00, None), (11, 1000.50, None)]
    assert _pick_amount_grn(grns, [1000.0])[0] == 10
