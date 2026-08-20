"""Realistic pharmaceutical mock data generator for Reports module.

Provides fallback demo data when synced POS tables have no records for a given store/period,
ensuring all 8 report views, columns, summaries, filters, and charts display immediately.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Tuple

_SUPPLIERS = [
    {"supplier_code": "SUP001", "supplier_name": "Sun Pharma Distributors Ltd"},
    {"supplier_code": "SUP002", "supplier_name": "Cipla Healthcare Agencies"},
    {"supplier_code": "SUP003", "supplier_name": "Abbott Healthcare Pvt Ltd"},
    {"supplier_code": "SUP004", "supplier_name": "Zydus Lifesciences Agency"},
    {"supplier_code": "SUP005", "supplier_name": "Mankind Medico Enterprises"},
    {"supplier_code": "SUP006", "supplier_name": "Glenmark Pharmaceuticals"},
    {"supplier_code": "SUP007", "supplier_name": "Torrent Pharma Distributors"},
    {"supplier_code": "SUP008", "supplier_name": "Alkem Laboratories Agency"},
    {"supplier_code": "SUP009", "supplier_name": "Dr. Reddy's Laboratories Supply"},
    {"supplier_code": "SUP010", "supplier_name": "Lupin Medico Distributors"},
    {"supplier_code": "SUP011", "supplier_name": "AstraZeneca India Agencies"},
    {"supplier_code": "SUP012", "supplier_name": "Intas Pharmaceuticals Supply"},
]

_PRODUCTS = [
    ("MED001", "Augmentin 625 Duo Tablet", "Sun Pharma Distributors Ltd", 10, Decimal("165.50"), Decimal("220.00"), "STRIP", "RACK-A1"),
    ("MED002", "Dolo 650mg Paracetamol Tablet", "Micro Labs Agency", 15, Decimal("24.80"), Decimal("34.50"), "STRIP", "RACK-A2"),
    ("MED003", "Pan 40mg Pantoprazole Tablet", "Alkem Laboratories Agency", 15, Decimal("98.20"), Decimal("142.00"), "STRIP", "RACK-A3"),
    ("MED004", "Azithral 500mg Azithromycin", "Alembic Pharma Agency", 5, Decimal("85.00"), Decimal("122.50"), "STRIP", "RACK-B1"),
    ("MED005", "Shelcal 500mg Calcium + D3", "Torrent Pharma Distributors", 15, Decimal("78.40"), Decimal("115.00"), "BOTTLE", "RACK-B2"),
    ("MED006", "Telma 40mg Telmisartan Tablet", "Glenmark Pharmaceuticals", 15, Decimal("142.00"), Decimal("210.00"), "STRIP", "RACK-B3"),
    ("MED007", "Glycomet GP 2 Forte Tablet", "USV Healthcare Agency", 15, Decimal("118.50"), Decimal("175.00"), "STRIP", "RACK-C1"),
    ("MED008", "Montek LC Montelukast + Levocet", "Sun Pharma Distributors Ltd", 10, Decimal("132.00"), Decimal("198.00"), "STRIP", "RACK-C2"),
    ("MED009", "Allegra 120mg Fexofenadine", "Sanofi India Agencies", 10, Decimal("145.00"), Decimal("218.00"), "STRIP", "RACK-C3"),
    ("MED010", "Pantocid DSR Capsule", "Sun Pharma Distributors Ltd", 15, Decimal("162.00"), Decimal("245.00"), "STRIP", "RACK-D1"),
    ("MED011", "Clavam 625 Amoxyclav Tablet", "Alkem Laboratories Agency", 10, Decimal("158.00"), Decimal("215.00"), "STRIP", "RACK-D2"),
    ("MED012", "Clexane 40mg Enoxaparin Injection", "Sanofi India Agencies", 1, Decimal("420.00"), Decimal("580.00"), "VIAL", "COLD-01"),
    ("MED013", "Huminsulin 30/70 100IU/ml Cartridge", "Eli Lilly Agency", 1, Decimal("395.00"), Decimal("545.00"), "VIAL", "COLD-02"),
    ("MED014", "Thyronorm 50mcg Thyroxine Tablet", "Abbott Healthcare Pvt Ltd", 120, Decimal("110.00"), Decimal("160.00"), "BOTTLE", "RACK-E1"),
    ("MED015", "Ecosprin 75mg Aspirin Tablet", "USV Healthcare Agency", 14, Decimal("4.20"), Decimal("6.50"), "STRIP", "RACK-E2"),
]


def get_mock_suppliers(query: str = "", limit: int = 30) -> List[Dict[str, str]]:
    q = (query or "").strip().lower()
    matches = [s for s in _SUPPLIERS if not q or q in s["supplier_name"].lower() or q in s["supplier_code"].lower()]
    return matches[:limit]


def get_mock_stock_adj(from_date: str, to_date: str) -> Tuple[List[str], List[Dict[str, Any]]]:
    cols = ["SNo", "ProductName", "TotalQuantity", "Expirydate", "SaleUnit", "PurchasePrice", "MRP", "Amount", "SeriesName"]
    types = ["Stock Adj", "Expiry Return", "Stock Adj", "Stock Adj", "Expiry Return", "Normal", "Stock Adj", "Normal"]
    rows = []
    
    for i, p in enumerate(_PRODUCTS[:10], start=1):
        qty = (i * 7) % 25 + 3
        stype = types[i % len(types)]
        price = p[4]
        amt = Decimal(qty) * price
        exp_date = (date.today() + timedelta(days=90 + (i * 45))).strftime("%Y-%m-%d")
        rows.append({
            "SNo": i,
            "ProductName": p[1],
            "TotalQuantity": qty,
            "Expirydate": exp_date,
            "SaleUnit": p[3],
            "PurchasePrice": float(price),
            "MRP": float(p[5]),
            "Amount": float(amt),
            "SeriesName": stype,
        })
    return cols, rows


def get_mock_sales_discount(from_date: str, to_date: str) -> Tuple[List[str], List[Dict[str, Any]]]:
    cols = ["Discount", "Amount", "Percentage"]
    slabs = [
        ("0%", Decimal("245000.00"), 48),
        ("5%", Decimal("112500.00"), 22),
        ("10%", Decimal("85400.00"), 17),
        ("15%", Decimal("42600.00"), 8),
        ("20%", Decimal("25300.00"), 5),
    ]
    rows = []
    for disc, amt, pct in slabs:
        rows.append({
            "Discount": disc,
            "Amount": float(amt),
            "Percentage": pct,
        })
    return cols, rows


def get_mock_monthly_sales(from_date: str, to_date: str) -> Tuple[List[str], List[Dict[str, Any]]]:
    cols = ["ReportDate", "SeriesName", "Amount"]
    rows = []

    try:
        f_dt = datetime.strptime(from_date[:10], "%Y-%m-%d").date()
        t_dt = datetime.strptime(to_date[:10], "%Y-%m-%d").date()
    except Exception:
        t_dt = date.today()
        f_dt = t_dt - timedelta(days=14)

    cur = f_dt
    series_list = ["Counter", "Retail", "Hospital", "Wholesale"]
    while cur <= t_dt:
        for idx, s in enumerate(series_list):
            base = 12000 + (cur.day * 650) + (idx * 3400)
            rows.append({
                "ReportDate": cur,
                "SeriesName": s,
                "Amount": Decimal(base),
            })
        cur += timedelta(days=1)

    return cols, rows


def get_mock_margin(from_date: str, to_date: str) -> Tuple[List[str], List[Dict[str, Any]]]:
    cols = ["SeriesName", "TotalTransactionAmount", "TotalItemCost", "TotalQuantity", "NumberOfBills", "ProfitValue", "MarginPercentage"]
    series_data = [
        ("Counter Retail", Decimal("485200"), Decimal("364000"), 4120, 940),
        ("Prescription / Hospital", Decimal("342000"), Decimal("251000"), 2850, 610),
        ("Wholesale / Bulk", Decimal("625000"), Decimal("512000"), 7890, 185),
        ("Institutional", Decimal("195000"), Decimal("148000"), 1640, 72),
    ]
    rows = []
    for s_name, sales, cost, qty, bills in series_data:
        profit = sales - cost
        margin_pct = int((profit / cost) * 100) if cost else 0
        rows.append({
            "SeriesName": s_name,
            "TotalTransactionAmount": int(sales),
            "TotalItemCost": int(cost),
            "TotalQuantity": int(qty),
            "NumberOfBills": int(bills),
            "ProfitValue": int(profit),
            "MarginPercentage": margin_pct,
        })
    return cols, rows


def get_mock_daily_margin(from_date: str, to_date: str) -> Tuple[List[str], List[Dict[str, Any]]]:
    cols = ["ReportDate", "C_Bills", "M_Bills", "R_Bills", "W_Bills", "Other_Txn", "TransactionAmount", "TotalItemCost", "ProfitValue", "C_Margin_Pct"]
    rows = []

    try:
        f_dt = datetime.strptime(from_date[:10], "%Y-%m-%d").date()
        t_dt = datetime.strptime(to_date[:10], "%Y-%m-%d").date()
    except Exception:
        t_dt = date.today()
        f_dt = t_dt - timedelta(days=7)

    cur = f_dt
    day_idx = 0
    while cur <= t_dt:
        c = Decimal(15400 + (day_idx * 720))
        m = Decimal(8900 + (day_idx * 410))
        r = Decimal(12300 + (day_idx * 550))
        w = Decimal(21000 + (day_idx * 1100))
        other = Decimal(1800)
        total_tx = c + m + r + w + other
        cost = Decimal(round(float(total_tx) * 0.74, 2))
        profit = total_tx - cost
        c_margin = round(float((c - (c * Decimal("0.74"))) / (c * Decimal("0.74")) * 100), 2)

        rows.append({
            "ReportDate": cur.strftime("%d-%m-%Y"),
            "C_Bills": float(c),
            "M_Bills": float(m),
            "R_Bills": float(r),
            "W_Bills": float(w),
            "Other_Txn": float(other),
            "TransactionAmount": float(total_tx),
            "TotalItemCost": float(cost),
            "ProfitValue": float(profit),
            "C_Margin_Pct": c_margin,
        })
        cur += timedelta(days=1)
        day_idx += 1

    return cols, rows


def get_mock_non_moving(dwell_days: int = 30, supplier_code: str = None) -> Tuple[List[str], List[Dict[str, Any]]]:
    cols = [
        "SupplierName", "SubLocation", "ProductCode", "ProductName",
        "TotalStock", "Batch_Stock", "StripQty", "ExpiryDate",
        "SaleUnit", "PurchasePrice", "MRP", "UnitDesc",
        "LastBillDate", "LastGRNDate", "SalesAge", "PurAge"
    ]
    rows = []
    for i, p in enumerate(_PRODUCTS, start=1):
        if supplier_code and supplier_code not in p[2]:
            continue
        sales_age = (dwell_days or 30) + 15 + (i * 12)
        pur_age = sales_age + 20
        last_bill = (date.today() - timedelta(days=sales_age)).strftime("%Y-%m-%d")
        last_grn = (date.today() - timedelta(days=pur_age)).strftime("%Y-%m-%d")
        exp_date = (date.today() + timedelta(days=120 + (i * 30))).strftime("%Y-%m-%d")
        stock = 45 + (i * 10)
        
        rows.append({
            "SupplierName": p[2],
            "SubLocation": p[7],
            "ProductCode": p[0],
            "ProductName": p[1],
            "TotalStock": stock,
            "Batch_Stock": stock,
            "StripQty": int(stock / p[3]) if p[3] else stock,
            "ExpiryDate": exp_date,
            "SaleUnit": p[3],
            "PurchasePrice": float(p[4]),
            "MRP": float(p[5]),
            "UnitDesc": p[6],
            "LastBillDate": last_bill,
            "LastGRNDate": last_grn,
            "SalesAge": sales_age,
            "PurAge": pur_age,
        })
    return cols, rows


def get_mock_purchased_not_sold(dwell_days: int = 30, supplier_code: str = None) -> Tuple[List[str], List[Dict[str, Any]]]:
    cols = [
        "SupplierName", "SubLocation", "ProductCode", "ProductName",
        "TotalStock", "Batch_Stock", "StripQty", "ExpiryDate",
        "SaleUnit", "PurchasePrice", "MRP", "UnitDesc",
        "LastBillDate", "LastGRNDate", "SalesAge", "PurAge"
    ]
    rows = []
    p_subset = _PRODUCTS[5:12]
    for i, p in enumerate(p_subset, start=1):
        if supplier_code and supplier_code not in p[2]:
            continue
        pur_age = (dwell_days or 30) + (i * 15)
        last_grn = (date.today() - timedelta(days=pur_age)).strftime("%Y-%m-%d")
        exp_date = (date.today() + timedelta(days=200 + (i * 25))).strftime("%Y-%m-%d")
        stock = 30 + (i * 8)
        
        rows.append({
            "SupplierName": p[2],
            "SubLocation": p[7],
            "ProductCode": p[0],
            "ProductName": p[1],
            "TotalStock": stock,
            "Batch_Stock": stock,
            "StripQty": int(stock / p[3]) if p[3] else stock,
            "ExpiryDate": exp_date,
            "SaleUnit": p[3],
            "PurchasePrice": float(p[4]),
            "MRP": float(p[5]),
            "UnitDesc": p[6],
            "LastBillDate": None,
            "LastGRNDate": last_grn,
            "SalesAge": None,
            "PurAge": pur_age,
        })
    return cols, rows


def get_mock_eyrus_7day(division_code: str = "") -> Tuple[List[str], List[Dict[str, Any]]]:
    today = date.today()
    days = [(today - timedelta(days=i)).strftime("%d/%m") for i in range(6, -1, -1)]
    cols = ["ProductCode", "ProductName", "Stock", *days, "Total_7D", "Value"]
    rows = []
    for idx, p in enumerate(_PRODUCTS[:10], start=1):
        day_sales = [(idx * 3 + d_i * 2) % 18 + 1 for d_i in range(7)]
        tot = sum(day_sales)
        val = Decimal(tot) * p[4]
        row_dict = {
            "ProductCode": p[0],
            "ProductName": p[1],
            "Stock": 85 + (idx * 12),
            "Total_7D": tot,
            "Value": float(val),
        }
        for d_str, s_val in zip(days, day_sales):
            row_dict[d_str] = s_val
        rows.append(row_dict)
    return cols, rows
