from __future__ import annotations

"""Procurement Decision Engine — business rules (pure Python, no I/O).

Implements the ratified Decision Engine rules PR-BR-001..016 exactly as defined
in docs/Procurement_Business_Rules.md, executed in the order of
docs/Procurement_Decision_Flow.md. Every function here is pure and unit-tested
against the catalogue's worked example (PARA-500).

No SQL and no side effects live in this module (mandatory: business rules are
Python, SQL is only for reading source data and bulk persistence).
"""

from dataclasses import dataclass

import math
from dataclasses import dataclass
from datetime import datetime, timedelta


# --------------------------------------------------------------------------
# Reason-code controlled vocabulary (PR-BR-015)
# --------------------------------------------------------------------------

INCLUDED_BELOW_MIN_DAYS = "INCLUDED_BELOW_MIN_DAYS"
EXCLUDED_NOT_SELLING = "EXCLUDED_NOT_SELLING"
EXCLUDED_ADEQUATE_COVER = "EXCLUDED_ADEQUATE_COVER"
EXCLUDED_FLAGGED = "EXCLUDED_FLAGGED"
EXCLUDED_INACTIVE = "EXCLUDED_INACTIVE"
EXCLUDED_ZERO_REQUIRED = "EXCLUDED_ZERO_REQUIRED"
# Legacy VB.NET eligibility gates ported for parity with order_local/remote.sql:
#   ps.lastsaledate >= DATEADD(day, -10, GETDATE())   (must have sold recently)
#   ps.lastsaledate >= ps.LastReceivedDate            (must have sold since the last GRN)
EXCLUDED_STALE_SALE = "EXCLUDED_STALE_SALE"
EXCLUDED_RECENTLY_RECEIVED = "EXCLUDED_RECENTLY_RECEIVED"

# Final-quantity determinant (PR-BR-009)
COVERAGE = "COVERAGE"
SPIKE_PROTECTION = "SPIKE_PROTECTION"
MAX_BILL_TRIGGER = "MAX_BILL_TRIGGER"

ACTION_INCLUDE = "INCLUDE"
ACTION_EXCLUDE = "EXCLUDE"


@dataclass(frozen=True)
class DecisionParameters:
    """Effective parameter set for a Refresh (PR-BR-016).

    Rolling/Min/Max come from the Refresh; classification cut-offs default to the
    ratified platform defaults until a parameter store exists.
    """

    rolling_days: int
    min_days: float
    max_days: float
    movement_fast_cut: float = 50.0
    movement_medium_cut: float = 10.0
    stock_low_cut: float = 3.0
    stock_safe_cut: float = 15.0
    # Legacy eligibility-gate constants (order_local/remote.sql). recency_days is
    # the "sold in the last N days" floor; as_of is the reference "now" (defaults
    # to wall-clock at evaluation) so the gate is deterministic under test.
    recency_days: int = 10
    as_of: datetime | None = None

    def validate(self):
        """PR-BR-005 exception: MaxDays >= MinDays > 0; RollingDays > 0."""
        if self.rolling_days is None or self.rolling_days <= 0:
            raise ValueError("rolling_days must be > 0")
        if self.min_days is None or self.min_days <= 0:
            raise ValueError("min_days must be > 0")
        if self.max_days is None or self.max_days < self.min_days:
            raise ValueError("max_days must be >= min_days")


# --------------------------------------------------------------------------
# Atomic rules
# --------------------------------------------------------------------------

def average_daily_sales(window_sales_qty, rolling_days):
    """PR-BR-002: AvgDailySales = WindowQty / RollingDays (full window length)."""
    if not rolling_days or rolling_days <= 0:
        return 0.0
    return (window_sales_qty or 0.0) / rolling_days


def effective_available(current_stock, pending_receivable, in_transit, reserved):
    """PR-BR-014: CurrentStock + PendingReceivable + ConfirmedInTransit - Reserved."""
    return ((current_stock or 0.0) + (pending_receivable or 0.0)
            + (in_transit or 0.0) - (reserved or 0.0))


def days_cover(effective_avail, avg_daily_sales):
    """PR-BR-003: EffectiveAvailable / AvgDailySales (0 if avg <= 0)."""
    if not avg_daily_sales or avg_daily_sales <= 0:
        return 0.0
    return effective_avail / avg_daily_sales


def movement_class(avg_daily_sales, params: DecisionParameters):
    """PR-BR-010: FAST >= fast_cut; MEDIUM >= medium_cut; SLOW > 0; else NONMOVING."""
    if avg_daily_sales >= params.movement_fast_cut:
        return "FAST"
    if avg_daily_sales >= params.movement_medium_cut:
        return "MEDIUM"
    if avg_daily_sales > 0:
        return "SLOW"
    return "NONMOVING"


def stock_status(effective_avail, cover, params: DecisionParameters):
    """PR-BR-011: OUT if avail<=0; LOW if cover<low; SAFE if cover<=safe; else OVERSTOCK."""
    if effective_avail <= 0:
        return "OUT"
    if cover < params.stock_low_cut:
        return "LOW"
    if cover <= params.stock_safe_cut:
        return "SAFE"
    return "OVERSTOCK"


def target_stock(avg_daily_sales, max_days):
    """PR-BR-005: TargetStockQty = AvgDailySales * MaxDays."""
    return avg_daily_sales * max_days


def coverage_required(target_stock_qty, effective_avail):
    """PR-BR-006: CoverageRequired = TargetStockQty - EffectiveAvailable."""
    return target_stock_qty - effective_avail


def final_required(target_stock_qty, effective_avail, max_day_sale_qty,
                   max_bill_qty, sale_unit=0.0):
    """PR-BR-007/008/009 (stock-netted): the demand floors are gross required
    STOCK LEVELS, and current stock is subtracted exactly once at the end.

    Legacy parity (order_local/remote.sql):

        maxqty   = MAX((slsqty/90)*maxDays, MaxSalesQtyInBill)   -- gross target incl. spike
        OrderQty = CEILING((maxqty - TotalStock) / SaleUnit)     -- ONE stock subtraction

    A spike floor (max-day / max-bill) is therefore a required stock LEVEL, not
    an extra order stacked on top of the stock already on hand. The previous
    implementation applied the floors to the *net* coverage requirement, i.e.
    ``MAX(target - stock, max_day, max_bill)``, which never subtracted stock from
    the spike floors and so over-ordered spiky-but-stocked products (e.g. order
    the full 300-unit single-day spike while 5 are already in stock). We now mirror
    legacy: gross target first, subtract stock once.

    Returns (required, final_required_qty, suggested_strip_qty, determinant).
    The determinant is the term that set the gross target, preferring COVERAGE
    (days-cover), then SPIKE_PROTECTION (max-day), then MAX_BILL_TRIGGER.
    When SaleUnit is missing/<=0 the strip quantity falls back to loose units.
    """
    target_stock_qty = target_stock_qty or 0.0
    effective_avail = effective_avail or 0.0
    max_day_sale_qty = max_day_sale_qty or 0.0
    max_bill_qty = max_bill_qty or 0.0
    gross_target = max(target_stock_qty, max_day_sale_qty, max_bill_qty)
    required = gross_target - effective_avail
    final_qty = max(0, math.ceil(required))
    if target_stock_qty >= gross_target:
        determinant = COVERAGE
    elif max_day_sale_qty >= gross_target:
        determinant = SPIKE_PROTECTION
    else:
        determinant = MAX_BILL_TRIGGER
    if sale_unit and sale_unit > 0:
        suggested_qty = math.ceil(final_qty / sale_unit)
    else:
        suggested_qty = final_qty
    return required, final_qty, suggested_qty, determinant


# --------------------------------------------------------------------------
# Full per-product evaluation (Stages 2-9)
# --------------------------------------------------------------------------

def evaluate(src: dict, params: DecisionParameters) -> dict:
    """Evaluate one product's source row into its decision snapshot fields.

    `src` carries the RAW inputs loaded from source (Stage 1):
      product identity, is_active, dont_consider,
      window_sales_qty, max_day_sale_qty, max_bill_qty, billing_frequency,
      current_stock, pending_receivable, in_transit, reserved.

    Returns a flat dict of columns for procurement_virtual_products, with an
    ``procurement_action`` of INCLUDE/EXCLUDE. Every product is evaluated here;
    the persistence layer (decision_service) writes only INCLUDE products to the
    VPL — the VPL is the procurement list, not a catalogue copy.
    """
    current_stock = src.get("current_stock", 0.0) or 0.0
    pending_receivable = src.get("pending_receivable", 0.0) or 0.0
    in_transit = src.get("in_transit", 0.0) or 0.0
    reserved = src.get("reserved", 0.0) or 0.0
    max_day = src.get("max_day_sale_qty", 0.0) or 0.0
    max_bill = src.get("max_bill_qty", 0.0) or 0.0
    sale_unit = src.get("sale_unit", 0.0) or 0.0

    # Stage 2 — metrics
    avg = average_daily_sales(src.get("window_sales_qty", 0.0), params.rolling_days)

    # Stage 3 — effective available (floored at 0 for cover purposes, PR-BR-014)
    eff_raw = effective_available(current_stock, pending_receivable, in_transit, reserved)
    eff = max(0.0, eff_raw)
    pending_used = pending_receivable + in_transit - reserved

    # Stage 4 — cover, movement class, stock status
    cover = days_cover(eff, avg)
    mclass = movement_class(avg, params)
    sstatus = stock_status(eff, cover, params)

    out = {
        "avg_daily_sales": avg,
        "window_sales_qty": src.get("window_sales_qty", 0.0) or 0.0,
        "max_day_sale_qty": max_day,
        "max_bill_qty": max_bill,
        "billing_frequency": src.get("billing_frequency", 0) or 0,
        "current_stock_qty": current_stock,
        "pending_purchase_qty": pending_receivable,
        "pending_sales_qty": reserved,
        "available_stock_qty": eff,
        "effective_available_qty": eff,
        "pending_used_qty": pending_used,
        "days_cover": cover,
        "movement_class": mclass,
        "stock_status": sstatus,
        # sizing defaults (populated below only for candidates)
        "target_days": None,
        "target_stock_qty": None,
        "raw_required_qty": None,
        "required_qty": None,
        "suggested_qty": 0,
        "final_required_qty": 0,
        "trigger_reason": None,
        "procurement_action": ACTION_EXCLUDE,
        "reason_code": None,
        "reason_text": None,
    }

    # Stage 5 — terminal exclusions (PR-BR-013) then candidate filter (PR-BR-004)
    if not src.get("is_active", True):
        out["reason_code"] = EXCLUDED_INACTIVE
        out["reason_text"] = "Excluded: product inactive."
        return out
    if src.get("dont_consider", False):
        out["reason_code"] = EXCLUDED_FLAGGED
        out["reason_text"] = "Excluded: marked do-not-order."
        return out
    if avg <= 0:
        out["reason_code"] = EXCLUDED_NOT_SELLING
        out["reason_text"] = "Excluded: no eligible sales in the rolling window."
        return out

    # HARD SKIP RULES — terminal, applied BEFORE any quantity sizing so an
    # ineligible product can never be re-introduced by a downstream calculation.
    # Fed by PRECISE real transaction dates (decision_repository: MAX sale
    # TransactionDate / MAX PurchaseTrans grndate), NOT month-level ProductTrans
    # aggregates, which cannot resolve "sold after the latest GRN".
    #
    #   Rule 1 (no sale in last N days): last real sale older than the recency
    #           floor → SKIP (legacy: ps.lastsaledate >= today-10).
    #   Rule 2 (no sale after latest GRN): a GRN exists AND the last real sale is
    #           strictly before it → just received, not yet moved → SKIP
    #           (legacy: ps.lastsaledate >= ps.LastReceivedDate, so same-day
    #           sale == GRN is KEPT). When no GRN exists the rule does not apply.
    last_sale = src.get("last_sale_date")
    last_recv = src.get("last_received_date")
    now = params.as_of or datetime.now()
    if last_sale is None or last_sale < now - timedelta(days=params.recency_days):
        out["reason_code"] = EXCLUDED_STALE_SALE
        out["reason_text"] = (
            f"Excluded: no sale in the last {params.recency_days} days."
        )
        return out
    if last_recv is not None and last_sale < last_recv:
        out["reason_code"] = EXCLUDED_RECENTLY_RECEIVED
        out["reason_text"] = (
            "Excluded: no sale since the latest GRN (recently received, not yet moved)."
        )
        return out

    if cover >= params.min_days:
        out["reason_code"] = EXCLUDED_ADEQUATE_COVER
        out["reason_text"] = (
            f"Excluded: {cover:.1f}d cover >= {params.min_days:g}d minimum."
        )
        return out

    # Included candidate — Stages 6-9. Gross target = MAX(days-cover target,
    # spike floors); subtract stock ONCE (see final_required — stock-netted).
    tgt = target_stock(avg, params.max_days)
    cov_req = coverage_required(tgt, eff)
    required, final_qty, suggested_qty, determinant = final_required(
        tgt, eff, max_day, max_bill, sale_unit
    )

    out["target_days"] = params.max_days
    out["target_stock_qty"] = tgt
    out["raw_required_qty"] = cov_req
    out["required_qty"] = required
    out["trigger_reason"] = determinant

    if final_qty <= 0:
        out["reason_code"] = EXCLUDED_ZERO_REQUIRED
        out["reason_text"] = "Excluded: already sufficiently covered (required <= 0)."
        return out

    gross_target = max(tgt, max_day, max_bill)
    out["procurement_action"] = ACTION_INCLUDE
    out["suggested_qty"] = suggested_qty
    out["final_required_qty"] = suggested_qty
    out["reason_code"] = INCLUDED_BELOW_MIN_DAYS
    out["reason_text"] = (
        f"Included; {suggested_qty} strip(s) ({final_qty} loose units); cover "
        f"{cover:.1f}d < min {params.min_days:g}d; driven by {determinant} "
        f"(gross target {gross_target:.0f} = max(cover {tgt:.0f}, "
        f"maxDay {max_day:g}, maxBill {max_bill:g}) - stock {eff:.0f})."
    )
    return out
