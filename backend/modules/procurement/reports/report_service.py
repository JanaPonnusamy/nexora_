import logging
from collections import defaultdict
from datetime import datetime
from calendar import monthrange

from fastapi import HTTPException

from modules.procurement.reports import repository
from modules.procurement.reports.aggregation_service import AggregationService

logger = logging.getLogger(__name__)


class ReportService:
    FALLBACK_SOURCE = "NEXORA"

    @staticmethod
    def _normalize_source(source):
        normalized = (source or "NEXORA").strip().upper()
        return "STORE_DB" if normalized == "STORE_DB" else "NEXORA"

    @staticmethod
    def _days_in_month(month_key):
        year, month = (month_key or "").split("-")
        return monthrange(int(year), int(month))[1]

    def _run_with_store_fallback(self, store, operation, *args, source="NEXORA"):
        normalized_source = self._normalize_source(source)
        try:
            result = operation(*args, normalized_source)
            return result, normalized_source
        except Exception:
            if normalized_source != "STORE_DB":
                raise
            logger.warning(
                "Falling back to %s for store %s (%s)",
                self.FALLBACK_SOURCE,
                store.get("store_name"),
                store.get("store_code"),
                exc_info=True,
            )
            result = operation(*args, self.FALLBACK_SOURCE)
            return result, self.FALLBACK_SOURCE

    def build_store_monthly_report(self, tenant_id, store_id, from_month, to_month, source="NEXORA"):
        try:
            product_rows = repository.product_monthly_summary(
                tenant_id, store_id, from_month, to_month, source
            )
            supplier_rows = repository.supplier_monthly_summary(
                tenant_id, store_id, from_month, to_month, source
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

    def build_store_summary(self, store, from_month, to_month, source="NEXORA"):
        try:
            rows, actual_source = self._run_with_store_fallback(
                store,
                self.build_store_monthly_report,
                store["tenant_id"],
                store["store_id"],
                from_month,
                to_month,
                source=source,
            )
            totals = AggregationService.calculate_totals(rows)
            totals["Store"] = store["store_name"]
            totals["StoreCode"] = store["store_code"]
            totals["StoreId"] = store["store_id"]
            totals["Status"] = "Success"
            totals["Source"] = actual_source
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
                "Source": self._normalize_source(source),
            }

    def build_multi_store_summary(self, tenant_id, from_month, to_month, source="NEXORA"):
        stores = repository.active_stores(tenant_id)
        return [self.build_store_summary(store, from_month, to_month, source) for store in stores]

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

    def dashboard(self, tenant_id, from_month, to_month, source="NEXORA"):
        if not tenant_id:
            raise HTTPException(status_code=400, detail="tenant_id is required")
        if not from_month or not to_month:
            raise HTTPException(status_code=400, detail="from_month and to_month are required")
        normalized_source = self._normalize_source(source)
        summary = self.build_multi_store_summary(tenant_id, from_month, to_month, normalized_source)
        return {
            "success": True,
            "source": normalized_source,
            "kpi": self.build_dashboard_totals(summary),
            "stores": summary,
        }

    def build_store_compare(self, store, month_a, month_b, source="NEXORA"):
        try:
            rows_a, source_a = self._run_with_store_fallback(
                store,
                self.build_store_monthly_report,
                store["tenant_id"],
                store["store_id"],
                month_a,
                month_a,
                source=source,
            )
            rows_b, source_b = self._run_with_store_fallback(
                store,
                self.build_store_monthly_report,
                store["tenant_id"],
                store["store_id"],
                month_b,
                month_b,
                source=source,
            )
            totals_a = AggregationService.calculate_totals(rows_a)
            totals_b = AggregationService.calculate_totals(rows_b)
            compare = AggregationService.calculate_compare(totals_a, totals_b)
            compare["AvgDailySalesA"] = round(
                totals_a["Sales"] / max(self._days_in_month(month_a), 1), 2
            )
            compare["AvgDailySalesB"] = round(
                totals_b["Sales"] / max(self._days_in_month(month_b), 1), 2
            )
            compare["AvgDailySalesGrowthPercent"] = AggregationService.growth_percent(
                compare["AvgDailySalesA"],
                compare["AvgDailySalesB"],
            )
            compare["Store"] = store["store_name"]
            compare["StoreCode"] = store["store_code"]
            compare["StoreId"] = store["store_id"]
            compare["Status"] = "Success"
            compare["Source"] = source_a if source_a == source_b else self.FALLBACK_SOURCE
            return compare
        except Exception as exc:
            logger.exception("Store compare failed")
            return {
                "Store": store.get("store_name"),
                "StoreCode": store.get("store_code"),
                "StoreId": store.get("store_id"),
                "Status": "Failed",
                "Error": str(exc),
                "Source": self._normalize_source(source),
            }

    def _build_compare_summary(self, rows, month_a, month_b):
        totals = {
            "SalesA": 0.0,
            "SalesB": 0.0,
            "StockA": 0.0,
            "StockB": 0.0,
            "PendingA": 0.0,
            "PendingB": 0.0,
        }
        ok_rows = [row for row in rows if row.get("Status") == "Success"]
        for row in ok_rows:
            for key in totals:
                totals[key] += float(row.get(key) or 0)

        compare = AggregationService.calculate_compare(
            {"Sales": totals["SalesA"], "ClosingStock": totals["StockA"], "PendingAmount": totals["PendingA"]},
            {"Sales": totals["SalesB"], "ClosingStock": totals["StockB"], "PendingAmount": totals["PendingB"]},
        )
        compare["StoresIncluded"] = len(ok_rows)
        compare["AvgDailySalesA"] = round(totals["SalesA"] / max(self._days_in_month(month_a), 1), 2)
        compare["AvgDailySalesB"] = round(totals["SalesB"] / max(self._days_in_month(month_b), 1), 2)
        compare["AvgDailySalesGrowthPercent"] = AggregationService.growth_percent(
            compare["AvgDailySalesA"],
            compare["AvgDailySalesB"],
        )
        compare["WorkingCapitalImpact"] = round(
            (totals["StockB"] - totals["StockA"]) + (totals["PendingA"] - totals["PendingB"]),
            2,
        )
        return compare

    def compare(self, tenant_id, month_a, month_b, source="NEXORA"):
        if not tenant_id:
            raise HTTPException(status_code=400, detail="tenant_id is required")
        if not month_a or not month_b:
            raise HTTPException(status_code=400, detail="month_a and month_b are required")
        normalized_source = self._normalize_source(source)
        stores = repository.active_stores(tenant_id)
        rows = [self.build_store_compare(store, month_a, month_b, normalized_source) for store in stores]
        return {
            "success": True,
            "source": normalized_source,
            "month_a": month_a,
            "month_b": month_b,
            "stores": rows,
            "summary": self._build_compare_summary(rows, month_a, month_b),
            "generated_at": datetime.now().isoformat(),
        }

    def store_analysis(self, tenant_id, store_id, from_month, to_month, source="NEXORA"):
        if not tenant_id or not store_id:
            raise HTTPException(status_code=400, detail="tenant_id and store_id are required")
        store = repository.store_by_id(tenant_id, store_id)
        if not store:
            raise HTTPException(status_code=404, detail="Store not found")
        rows, actual_source = self._run_with_store_fallback(
            store,
            self.build_store_monthly_report,
            tenant_id,
            store_id,
            from_month,
            to_month,
            source=source,
        )
        return {
            "success": True,
            "source": actual_source,
            "store": store["store_name"],
            "store_name": store["store_name"],
            "store_code": store["store_code"],
            "store_id": store["store_id"],
            "rows": rows,
        }
