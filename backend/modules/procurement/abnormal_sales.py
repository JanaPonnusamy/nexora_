"""Abnormal bill-sale detection (rulebook PRR-SALE-ABNORMAL / PRR-SALE-WARNING).

One bill that sells far more of a product than its usual bill (a bulk or
institutional sale -- e.g. Evion, Munch) inflates the average daily sales the
order quantity is built from. These rules find such bills so the Purchase
Manager can review them and mark the sale "do not consider in order"
(ProductSaleInformation.DontConsiderInOrder), which both the legacy order SQL
and the Nexora decision engine already exclude from demand.

Pure functions only: callers load the bills (legacy OrderNMC or platform
sync.*) and pass them in.

Rule, per product over the sales window:
  * bill qty   = the product's quantity on one bill (all its lines summed);
  * usual bill = the average qty of the product's OTHER counted bills -- the
    bill being tested is left out, otherwise one huge bill raises its own
    average and can never look abnormal on a product with few bills;
  * counted    = not already marked DontConsiderInOrder;
  * ratio      = bill qty / usual bill, only when at least MIN_OTHER_BILLS
    other counted bills exist (no average to compare against otherwise);
  * ratio >= ABNORMAL_MULTIPLIER -> 'abnormal' (listed first for PM review);
  * ratio >= WARNING_MULTIPLIER  -> 'warning'  (warning shown at review time).
"""

from __future__ import annotations

ABNORMAL_MULTIPLIER = 5.0
WARNING_MULTIPLIER = 3.0
MIN_OTHER_BILLS = 2
WINDOW_DAYS = 90

LEVEL_ABNORMAL = "abnormal"
LEVEL_WARNING = "warning"


def _level(ratio, abnormal, warning):
    if ratio is None:
        return None
    if ratio >= abnormal:
        return LEVEL_ABNORMAL
    if ratio >= warning:
        return LEVEL_WARNING
    return None


def classify_product(bills, abnormal=ABNORMAL_MULTIPLIER, warning=WARNING_MULTIPLIER, min_other=MIN_OTHER_BILLS):
    """Classify one product's bills.

    bills: iterable of dicts with at least ``qty`` (> 0) and ``dont_consider``
    (bool); any other keys (bill_no, bill_date, customer...) are passed through.

    Returns None when nothing is flagged, else a summary dict:
      level         'abnormal' | 'warning' | 'reviewed' -- 'reviewed' when the
                    only flagged bills are already marked do-not-consider;
      avg_bill_qty  average of all counted bills;
      bill_count    number of counted bills;
      max_ratio     highest ratio among counted flagged bills (or excluded
                    ones when level is 'reviewed');
      bills         the flagged bills (counted or excluded), highest ratio
                    first, each with avg_other / ratio / level / dont_consider.
    """
    rows = [dict(b) for b in bills if float(b.get("qty") or 0) > 0]
    counted = [b for b in rows if not b.get("dont_consider")]
    total = sum(float(b["qty"]) for b in counted)
    n = len(counted)

    flagged = []
    for b in rows:
        qty = float(b["qty"])
        excluded = bool(b.get("dont_consider"))
        others_n = n if excluded else n - 1
        others_sum = total if excluded else total - qty
        if others_n < min_other or others_sum <= 0:
            continue
        avg_other = others_sum / others_n
        ratio = qty / avg_other
        level = _level(ratio, abnormal, warning)
        if level is None:
            continue
        b.update({
            "qty": qty,
            "dont_consider": excluded,
            "avg_other": round(avg_other, 2),
            "ratio": round(ratio, 1),
            "level": level,
        })
        flagged.append(b)

    if not flagged:
        return None
    flagged.sort(key=lambda b: b["ratio"], reverse=True)
    live = [b for b in flagged if not b["dont_consider"]]
    if any(b["level"] == LEVEL_ABNORMAL for b in live):
        level = LEVEL_ABNORMAL
    elif live:
        level = LEVEL_WARNING
    else:
        level = "reviewed"
    return {
        "level": level,
        "avg_bill_qty": round(total / n, 2) if n else None,
        "bill_count": n,
        "max_ratio": (live or flagged)[0]["ratio"],
        "bills": flagged,
    }


def classify_bills(bill_rows, **thresholds):
    """Group flat bill rows by product_code and classify each product.

    bill_rows: dicts with product_code, qty, dont_consider (+ pass-through
    keys). Returns {product_code: summary} for flagged products only.
    """
    by_product: dict[str, list] = {}
    for row in bill_rows:
        by_product.setdefault(str(row["product_code"]), []).append(row)
    out = {}
    for code, bills in by_product.items():
        summary = classify_product(bills, **thresholds)
        if summary:
            summary["product_code"] = code
            out[code] = summary
    return out
