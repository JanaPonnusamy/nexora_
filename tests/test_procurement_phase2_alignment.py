"""Procurement Phase 2 — schema/convention alignment tests.

DB-free: validates the Pydantic contracts and the SQL migration DDL against the
approved Phase 2 changes and the NEXORA_PLATFORM conventions. No connection is
opened, so these run anywhere.
"""

import os
import re
import sys

# Make `backend/` importable regardless of pytest rootdir.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BACKEND = os.path.join(_REPO_ROOT, "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from modules.procurement.schemas import CycleCreate, CycleOut  # noqa: E402
from modules.procurement.vpl_schemas import (  # noqa: E402
    VplCreate, VplOut, VpProductOut,
)

_SQL_DIR = os.path.join(_BACKEND, "modules", "procurement", "sql")


def _sql(name):
    with open(os.path.join(_SQL_DIR, name), encoding="utf-8") as fh:
        return fh.read()


def _ddl(name):
    """SQL with /* */ block and -- line comments stripped, so assertions match
    real DDL rather than the descriptive header comments."""
    text = _sql(name)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"--[^\n]*", "", text)
    return text


# --------------------------------------------------------------------------
# Pydantic contracts
# --------------------------------------------------------------------------

def test_cycle_create_accepts_boundary_numbers():
    c = CycleCreate(
        tenant_id="t1", name="Cycle 1",
        start_grn_number="G100", start_sale_bill_number="S100",
        end_grn_number="G200", end_sale_bill_number="S200",
    )
    assert c.start_grn_number == "G100"
    assert c.end_sale_bill_number == "S200"


def test_cycle_out_exposes_boundary_and_active_refresh():
    fields = CycleOut.model_fields
    for f in (
        "start_grn_number", "start_sale_bill_number",
        "end_grn_number", "end_sale_bill_number", "active_refresh_id",
    ):
        assert f in fields


def test_vpl_create_accepts_refresh_parameters():
    v = VplCreate(
        tenant_id="t1", cycle_id="c1", snapshot_name="R1",
        rolling_days=90, min_days=10, max_days=20,
        previous_refresh_id="r0", snapshot_grn_number="G1",
        snapshot_sale_bill_number="S1", sync_execution_id="e1",
    )
    assert v.rolling_days == 90
    assert v.previous_refresh_id == "r0"


def test_refresh_pk_renamed_to_refresh_id():
    assert "refresh_id" in VplOut.model_fields
    assert "id" not in VplOut.model_fields
    # previous_pending_ref is intentionally absent (pending derived from remaining_qty)
    assert "previous_pending_ref" not in VplOut.model_fields


def test_virtual_product_out_uses_platform_pk_and_fk():
    fields = VpProductOut.model_fields
    assert "virtual_product_id" in fields
    assert "refresh_id" in fields
    assert "vpl_id" not in fields
    assert "id" not in fields


# --------------------------------------------------------------------------
# Migration DDL — approved column changes
# --------------------------------------------------------------------------

def test_cycle_ddl_boundary_added_runtime_removed():
    ddl = _ddl("0001_procurement_tables.sql")
    for added in (
        "start_grn_number", "start_sale_bill_number",
        "end_grn_number", "end_sale_bill_number", "active_refresh_id",
    ):
        assert added in ddl
    for removed in (
        "rolling_days", "generated_product_count",
        "live_refresh_count", "last_refresh_id",
    ):
        assert removed not in ddl


def test_refresh_ddl_has_parameters_no_pending_ref():
    ddl = _ddl("0002_virtual_product_list.sql")
    for col in (
        "refresh_id", "rolling_days", "previous_refresh_id",
        "snapshot_grn_number", "snapshot_sale_bill_number", "sync_execution_id",
    ):
        assert col in ddl
    assert "previous_pending_ref" not in ddl
    assert "generation_duration" not in ddl


def test_virtual_products_have_explainability_columns():
    ddl = _ddl("0002_virtual_product_list.sql")
    assert "virtual_product_id" in ddl
    assert "effective_available_qty" in ddl
    assert "pending_used_qty" in ddl
    assert "vpl_id" not in ddl  # renamed to refresh_id


def test_assignments_have_export_tracking():
    ddl = _sql("0005_procurement_order_item_assignments.sql")
    for col in (
        "assignment_id", "export_batch_number", "export_split_number",
        "export_uid", "exported_at", "exported_by",
    ):
        assert col in ddl


def test_order_items_status_supports_review():
    ddl = _sql("0004_procurement_order_items.sql")
    assert "review" in ddl
    assert "order_item_id" in ddl
    assert "refresh_id" in ddl


# --------------------------------------------------------------------------
# Platform conventions applied to every table
# --------------------------------------------------------------------------

_ALL = (
    "0001_procurement_tables.sql",
    "0002_virtual_product_list.sql",
    "0004_procurement_order_items.sql",
    "0005_procurement_order_item_assignments.sql",
)


def test_no_named_constraints_and_no_nvarchar_or_datetime2():
    for name in _ALL:
        ddl = _ddl(name)
        assert "NVARCHAR" not in ddl, name
        assert "DATETIME2" not in ddl, name
        # unnamed inline constraints (platform style)
        assert "CONSTRAINT PK_" not in ddl, name
        assert "CONSTRAINT DF_" not in ddl, name
        assert "CONSTRAINT FK_" not in ddl, name


def test_soft_delete_consistent_on_header_tables():
    for name in _ALL:
        ddl = _sql(name)
        for col in ("is_deleted", "deleted_at", "deleted_by"):
            assert col in ddl, f"{col} missing in {name}"
