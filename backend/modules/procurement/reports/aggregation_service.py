import logging

logger = logging.getLogger(__name__)


class AggregationService:
    @staticmethod
    def safe_float(value):
        try:
            if value is None:
                return 0.0
            return float(value)
        except Exception:
            return 0.0

    @classmethod
    def calculate_metrics(cls, row):
        sales = cls.safe_float(row.get("Sales"))
        purchase = cls.safe_float(row.get("Purchase"))
        purchase_return = cls.safe_float(row.get("PurchaseReturn"))
        opening_stock = cls.safe_float(row.get("OpeningStock"))
        transfer_in = cls.safe_float(row.get("TransferIn"))
        transfer_out = cls.safe_float(row.get("TransferOut"))
        adjustment = cls.safe_float(row.get("Adjustment"))
        closing_stock = cls.safe_float(row.get("ClosingStock"))
        cost_of_sales = cls.safe_float(row.get("CostOfSales"))
        pending_amount = cls.safe_float(row.get("PendingAmount"))
        pending_invoices = cls.safe_float(row.get("PendingInvoices"))

        gp = sales - cost_of_sales
        gp_percent = 0 if sales == 0 else round((gp / sales) * 100, 2)
        purchase_sales_ratio = 0 if sales == 0 else round(purchase / sales, 4)
        stock_pending_ratio = (
            0 if pending_amount == 0 else round(closing_stock / pending_amount, 4)
        )

        return {
            "Sales": sales,
            "Purchase": purchase,
            "PurchaseReturn": purchase_return,
            "OpeningStock": opening_stock,
            "TransferIn": transfer_in,
            "TransferOut": transfer_out,
            "Adjustment": adjustment,
            "ClosingStock": closing_stock,
            "CostOfSales": cost_of_sales,
            "PendingAmount": pending_amount,
            "PendingInvoices": pending_invoices,
            "GP": round(gp, 2),
            "GPPercent": gp_percent,
            "PurchaseSalesRatio": purchase_sales_ratio,
            "StockPendingRatio": stock_pending_ratio,
        }

    @classmethod
    def merge_product_supplier(cls, product_row, supplier_row):
        combined = {}
        if product_row:
            combined.update(dict(product_row))
        if supplier_row:
            combined.update(dict(supplier_row))
        combined.update(cls.calculate_metrics(combined))
        return combined

    SUMMED_KEYS = (
        "Sales",
        "Purchase",
        "PurchaseReturn",
        "TransferIn",
        "TransferOut",
        "Adjustment",
        "CostOfSales",
    )
    # Point-in-time balances: never summed across months.
    SNAPSHOT_KEYS = ("ClosingStock", "PendingAmount", "PendingInvoices")

    @classmethod
    def calculate_totals(cls, rows):
        totals = {key: 0 for key in cls.SUMMED_KEYS}
        for key in cls.SNAPSHOT_KEYS:
            totals[key] = 0
        totals["OpeningStock"] = 0

        if not rows:
            return cls.calculate_metrics(totals)

        sorted_rows = sorted(rows, key=lambda row: row.get("MonthOfStatistics"))

        for row in sorted_rows:
            for key in cls.SUMMED_KEYS:
                totals[key] += cls.safe_float(row.get(key))

        totals["OpeningStock"] = cls.safe_float(sorted_rows[0].get("OpeningStock"))
        last_row = sorted_rows[-1]
        for key in cls.SNAPSHOT_KEYS:
            totals[key] = cls.safe_float(last_row.get(key))

        return cls.calculate_metrics(totals)

    @classmethod
    def growth_percent(cls, value_a, value_b):
        if value_a == 0:
            return 0.0 if value_b == 0 else 100.0
        return round((value_b - value_a) / abs(value_a) * 100, 2)

    @classmethod
    def paid_up_stock(cls, closing_stock, pending_amount):
        paid_up_value = closing_stock - pending_amount
        paid_up_percent = 0.0 if closing_stock == 0 else round((paid_up_value / closing_stock) * 100, 2)
        return paid_up_value, paid_up_percent

    @classmethod
    def calculate_compare(cls, totals_a, totals_b):
        paid_up_a, paid_up_percent_a = cls.paid_up_stock(
            totals_a["ClosingStock"], totals_a["PendingAmount"]
        )
        paid_up_b, paid_up_percent_b = cls.paid_up_stock(
            totals_b["ClosingStock"], totals_b["PendingAmount"]
        )
        return {
            "SalesA": totals_a["Sales"],
            "SalesB": totals_b["Sales"],
            "SalesGrowthPercent": cls.growth_percent(totals_a["Sales"], totals_b["Sales"]),
            "StockA": totals_a["ClosingStock"],
            "StockB": totals_b["ClosingStock"],
            "StockGrowthPercent": cls.growth_percent(totals_a["ClosingStock"], totals_b["ClosingStock"]),
            "PendingA": totals_a["PendingAmount"],
            "PendingB": totals_b["PendingAmount"],
            "PaidUpStockA": round(paid_up_a, 2),
            "PaidUpStockPercentA": paid_up_percent_a,
            "PaidUpStockB": round(paid_up_b, 2),
            "PaidUpStockPercentB": paid_up_percent_b,
        }
