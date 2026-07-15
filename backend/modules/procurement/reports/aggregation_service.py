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

    @classmethod
    def calculate_totals(cls, rows):
        totals = {
            "Sales": 0,
            "Purchase": 0,
            "PurchaseReturn": 0,
            "OpeningStock": 0,
            "TransferIn": 0,
            "TransferOut": 0,
            "Adjustment": 0,
            "ClosingStock": 0,
            "CostOfSales": 0,
            "PendingAmount": 0,
            "PendingInvoices": 0,
        }
        for row in rows:
            for key in totals:
                totals[key] += cls.safe_float(row.get(key))
        return cls.calculate_metrics(totals)
