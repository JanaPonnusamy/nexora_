import logging
from collections import defaultdict

from fastapi import HTTPException

from modules.procurement.reports import repository
from modules.procurement.reports.aggregation_service import AggregationService

logger = logging.getLogger(__name__)


class ReportService:
    def build_store_monthly_report(self, tenant_id, store_id, from_month, to_month):
        try:
            product_rows = repository.product_monthly_summary(
                tenant_id, store_id, from_month, to_month
            )
            supplier_rows = repository.supplier_monthly_summary(
                tenant_id, store_id, from_month, to_month
            )
            supplier_lookup = {row["MonthOfStatistics"]: row for row in supplier_rows}

            results = []
            for product_row in product_rows:
                month = product_row["MonthOfStatistics"]
                final_row = AggregationService.merge_product_supplier(
                    product_row,
                    supplier_lookup.get(month),
                )
                final_row["MonthOfStatistics"] = month
                results.append(final_row)
            return results
        except Exception:
            logger.exception("Store monthly report failed")
            raise

    def build_store_summary(self, store, from_month, to_month):
        try:
            rows = self.build_store_monthly_report(
                store["tenant_id"],
                store["store_id"],
                from_month,
                to_month,
            )
            totals = AggregationService.calculate_totals(rows)
            totals["Store"] = store["store_name"]
            totals["StoreCode"] = store["store_code"]
            totals["StoreId"] = store["store_id"]
            totals["Status"] = "Success"
            return totals
        except Exception as exc:
            logger.exception("Store summary failed")
            return {
                "Store": store.get("store_name"),
                "StoreCode": store.get("store_code"),
                "StoreId": store.get("store_id"),
                "Status": "Failed",
                "Error": str(exc),
                "Sales": 0,
                "Purchase": 0,
                "PurchaseReturn": 0,
                "ClosingStock": 0,
                "PendingAmount": 0,
                "PendingInvoices": 0,
                "GP": 0,
                "GPPercent": 0,
                "PurchaseSalesRatio": 0,
                "StockPendingRatio": 0,
            }

    def build_multi_store_summary(self, tenant_id, from_month, to_month):
        stores = repository.active_stores(tenant_id)
        return [self.build_store_summary(store, from_month, to_month) for store in stores]

    def build_dashboard_totals(self, store_summary_rows):
        totals = defaultdict(float)
        for row in store_summary_rows:
            totals["Sales"] += row.get("Sales", 0)
            totals["Purchase"] += row.get("Purchase", 0)
            totals["ClosingStock"] += row.get("ClosingStock", 0)
            totals["PendingAmount"] += row.get("PendingAmount", 0)
            totals["PendingInvoices"] += row.get("PendingInvoices", 0)
            totals["GP"] += row.get("GP", 0)
        sales = totals["Sales"]
        totals["GPPercent"] = 0 if sales == 0 else round((totals["GP"] / sales) * 100, 2)
        return dict(totals)

    def dashboard(self, tenant_id, from_month, to_month):
        if not tenant_id:
            raise HTTPException(status_code=400, detail="tenant_id is required")
        if not from_month or not to_month:
            raise HTTPException(status_code=400, detail="from_month and to_month are required")
        summary = self.build_multi_store_summary(tenant_id, from_month, to_month)
        return {
            "success": True,
            "kpi": self.build_dashboard_totals(summary),
            "stores": summary,
        }

    def store_analysis(self, tenant_id, store_id, from_month, to_month):
        if not tenant_id or not store_id:
            raise HTTPException(status_code=400, detail="tenant_id and store_id are required")
        store = repository.store_by_id(tenant_id, store_id)
        if not store:
            raise HTTPException(status_code=404, detail="Store not found")
        return {
            "success": True,
            "store": store["store_name"],
            "store_name": store["store_name"],
            "store_code": store["store_code"],
            "store_id": store["store_id"],
            "rows": self.build_store_monthly_report(tenant_id, store_id, from_month, to_month),
        }
