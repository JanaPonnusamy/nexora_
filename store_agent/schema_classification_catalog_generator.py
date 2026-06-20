
import json
from pathlib import Path


class SchemaClassificationCatalogGenerator:

    MASTER_TABLES = {
        "Products",
        "ProductSaleInformation",
        "ProductSupplierLink",
        "ProductLocationLink",
        "ProductDrug",
        "ProductGroup",
        "ProductUOM",
        "Suppliers",
        "Customers",
        "Manufacturers",
        "HSN",
        "Divisions",
        "Drug",
        "Strength",
        "RackMaster",
        "BrandMaster",
        "CategoryMaster"
    }

    TRANSACTION_TABLES = {
        "Purchasetrans",
        "Mpurchasetrans",
        "H_Purchasetrans",
        "SaleInformation",
        "MSaleInformation",
        "H_SaleInformation",
        "SalesOrderHeader",
        "SalesOrderDetail",
        "SalesCreditDebitInfo",
        "PurchaseCreditDebitInfo",
        "BillPayments",
        "CustomerTrans",
        "Suppliertrans",
        "STrans",
        "TTrans"
    }

    INVENTORY_TABLES = {
        "Batches",
        "H_Batches",
        "MonthEndBatches",
        "ProductTrans",
        "ProductTransDay",
        "StockCorrection",
        "DailyStockDetail",
        "DailyStockHeader",
        "PhysicalInventory",
        "PhysicalInventoryDetail",
        "ExpiryBatches",
        "RejectedBatches"
    }

    SYSTEM_TABLES = {
        "AuditLog",
        "EventLog",
        "MasterLog",
        "SyncDetail",
        "SyncErrorLog",
        "ShopaidSyncDetail",
        "Settings4Shortcutkey",
        "MasterSettings",
        "MenuPermission4Roles"
    }

    def generate(
        self,
        snapshot_file,
        output_file
    ):

        with open(
            snapshot_file,
            "r",
            encoding="utf-8"
        ) as fp:
            snapshot = json.load(fp)

        catalog = {}

        for table in snapshot["tables"]:

            table_name = table["table_name"]

            if (
                table_name.startswith("Temp")
                or table_name.startswith("temp")
                or table_name.startswith("H_")
                or table_name.startswith("M_")
                or table_name.startswith("Ins_")
                or "bak" in table_name.lower()
            ):
                catalog[table_name] = "EXCLUDED"

            elif table_name in self.MASTER_TABLES:
                catalog[table_name] = "MASTER"

            elif table_name in self.TRANSACTION_TABLES:
                catalog[table_name] = "TRANSACTION"

            elif table_name in self.INVENTORY_TABLES:
                catalog[table_name] = "INVENTORY"

            elif table_name in self.SYSTEM_TABLES:
                catalog[table_name] = "SYSTEM"

            else:
                catalog[table_name] = "UNCLASSIFIED"

        output_path = Path(output_file)

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        with open(
            output_path,
            "w",
            encoding="utf-8"
        ) as fp:
            json.dump(
                catalog,
                fp,
                indent=4
            )

        return catalog
