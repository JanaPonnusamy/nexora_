using System;
using System.Collections.Generic;
using System.Data;
using System.Data.SqlClient;
using System.Diagnostics;
using System.Linq;
using System.Text;

namespace NMVSyncAgent
{
    /// <summary>
    /// POS (Shopaid, store LAN) → local OrderNMC. Replaces the VB "Sync" button for NMV.
    /// Source queries are copied from VB CentralSyncHelper.GetQueryForTable so the data the
    /// VB screens see is unchanged. Differences (deliberate, safer): merge keys = destination PK,
    /// #temp staging, per-batch transaction, update only rows whose values changed, real error reporting.
    /// </summary>
    public class PosTable
    {
        public string Name;          // logical / source table name
        public string Dest;          // destination table in OrderNMC
        public string Mode;          // full | id_watermark | si_window
        public string Query;         // source SELECT (may use @Param1)
    }

    public class PosSync
    {
        readonly AgentConfig _c;
        public PosSync(AgentConfig c) { _c = c; }

        // ---- source queries: verbatim from CentralSyncHelper.GetQueryForTable (VB) ----
        public static readonly PosTable Products = new PosTable { Name = "Products", Dest = "Products", Mode = "full",
            Query = "SELECT ProductCode, ProductName, DivisionCode, ManufacturerCode, SupplierCode, UnitDescription, AllowFractions, MinimumStockLevel, MaximumStockLevel, ScheduleCode, MRP, PurchasePrice, PurchaseUnit, PurchaseTaxCode, SalePrice, SaleUnit, SalesTaxCode, TotalStock, Remarks, ProductType, TaxId, ItemCost, SubLocation, CreationDate, ModifiedDate, isActive, OrderDate, OrderTime, FreeQuantity FROM Products WHERE isActive = 1" };
        public static readonly PosTable ProductSaleInformation = new PosTable { Name = "ProductSaleInformation", Dest = "ProductSaleInformation", Mode = "id_watermark",
            Query = "SELECT PS.ProductCode, PS.Quantity, PS.ID, PS.TransactionDate, PS.SeriesTransID, PS.TransactionValidity, PS.DontConsiderInOrder, PS.Bnumber, PS.SeriesName, PS.MRP, PS.PurchasePrice, PS.DiscountPercentage, PS.LastAdjustmentDate, PS.BillNumber,ps.Batchdescription,PS.ExpiryDate,ps.rate1 FROM ProductSaleInformation PS WHERE PS.ID > @Param1 AND PS.TransactionValidity = 0" };
        public static readonly PosTable Suppliers = new PosTable { Name = "Suppliers", Dest = "OrderSuppliers", Mode = "full",
            Query = "SELECT DISTINCT suppliercode, suppliername, mobilenumber, email FROM Suppliers WHERE IsActive = 1" };
        public static readonly PosTable Batches = new PosTable { Name = "Batches", Dest = "Batches", Mode = "full",
            Query = "SELECT ProductCode, Stock, MRP, ExpiryDate, ItemCost, PurchasePrice, SaleUnit, GrnDate, LastReceivedDate, LastSaleDate, BatchCode, SalesTaxCode, SupplierCode, Rate1 FROM Batches WHERE Stock > 0" };
        public static readonly PosTable ProductTrans = new PosTable { Name = "ProductTrans", Dest = "ProductTrans", Mode = "full",
            Query = "WITH LastThreeMonths AS (SELECT * FROM ProductTrans WHERE MonthOfStatistics >= DATEADD(MONTH, -4, GETDATE())) SELECT MonthOfStatistics, SaleQuantity, StockInHand, PurchaseQuantity, AdjustmentQuantity, LastBillDate, LastGrnDate, ProductCode FROM LastThreeMonths WHERE StockInHand IS NOT NULL AND PurchaseQuantity IS NOT NULL AND SaleQuantity IS NOT NULL AND AdjustmentQuantity IS NOT NULL ORDER BY ProductCode, MonthOfStatistics" };
        public static readonly PosTable PurchaseTrans = new PosTable { Name = "PurchaseTrans", Dest = "PurchaseTrans", Mode = "id_watermark",
            Query = "SELECT PT.ID, p.productcode, P.ProductType, pt.stockreceived, pt.FreeQty, ProductDiscPercent, pt.itemcost, pt.purchaseprice, pt.mrp, pt.grndate, pt.InvoiceSeries, pt.Grnnumber, s.suppliername, pt.suppliercode FROM PurchaseTrans pt INNER JOIN suppliers s ON pt.suppliercode = s.suppliercode INNER JOIN products p ON p.productcode = pt.productcode WHERE pt.id > @Param1 ORDER BY pt.id DESC" };
        public static readonly PosTable SaleInformation = new PosTable { Name = "SaleInformation", Dest = "SaleInformation", Mode = "si_window",
            Query = "SELECT SI.BillDate, SI.BillNumber, SI.BNumber, SI.BillAmount, SI.CustomerName, SI.DeliverySalesRep, SI.Billtime, SI.CustomerCode FROM SaleInformation SI WHERE EXISTS ( SELECT 1 FROM ProductSaleInformation PS WHERE PS.ID >  @Param1 AND PS.TransactionValidity = 0 AND PS.BNumber = SI.BNumber AND PS.TransactionDate = SI.BillDate ) ORDER BY SI.BillDate, SI.BillNumber" };
        public static readonly PosTable SalesRep = new PosTable { Name = "SalesRep", Dest = "SalesRep", Mode = "full",
            Query = "SELECT DISTINCT Salesmancode, Salesmanname, CreationDate, ModifiedDate FROM SalesRep WHERE isactive = 1" };
        public static readonly PosTable SupplierProductMatch = new PosTable { Name = "SupplierProductMatch", Dest = "SupplierProductMatch", Mode = "full",
            Query = "SELECT suppliercode, supplierproductcode, supplierproductname, productcode, username, lastmodifieddate, isactive FROM SupplierProductMatch" };

        public List<PosTable> MasterTables()
        {
            var l = new List<PosTable> { Products, Batches, SalesRep, SupplierProductMatch };
            if (_c.pos_sync_ordersuppliers) l.Add(Suppliers);
            return l;
        }

        // SaleInformation must run before ProductSaleInformation (VB order; its window is based on the pre-sync PSI max ID)
        public List<PosTable> IncrementalTables() { return new List<PosTable> { SaleInformation, ProductTrans, PurchaseTrans, ProductSaleInformation }; }

        /// <summary>Runs a list of tables; returns false if any failed.</summary>
        public bool RunCategory(string category, List<PosTable> tables)
        {
            bool allOk = true;
            Log.Info("POS", category + " start (" + string.Join(",", tables.Select(t => t.Name)) + ")");
            using (var local = Db.OpenLocal(_c))
            using (var pos = Db.OpenPos(_c))
            {
                Log.Info("POS", "connected local=" + _c.local_server + "/" + _c.local_database + " pos=" + pos.DataSource + "/" + pos.Database);
                foreach (var t in tables)
                {
                    var sw = Stopwatch.StartNew();
                    try
                    {
                        int examined, changed;
                        string wm = SyncTable(pos, local, t, out examined, out changed);
                        Log.Info("POS", string.Format("{0,-24} OK examined={1} changed={2} watermark={3} dur={4}ms", t.Name, examined, changed, wm, sw.ElapsedMilliseconds));
                        Db.Audit(local, category, t.Name, "MERGE", examined, changed, "OK", sw.ElapsedMilliseconds, "watermark=" + wm);
                        Db.SetState(local, "pos_last_ok:" + t.Name, DateTimeOffset.Now.ToString("o"));
                    }
                    catch (Exception ex)
                    {
                        allOk = false;
                        Log.Error("POS", t.Name + " FAILED", ex);
                        Db.Audit(local, category, t.Name, "MERGE", null, null, "FAILED", sw.ElapsedMilliseconds, ex.Message);
                    }
                }
            }
            Log.Info("POS", category + " end ok=" + allOk);
            return allOk;
        }

        string SyncTable(SqlConnection pos, SqlConnection local, PosTable t, out int examined, out int changed)
        {
            examined = 0; changed = 0;
            string store = _c.store_name;

            // watermark derived from destination (same as VB) — cannot drift from what is actually stored
            long param = 0; bool hasParam = false;
            if (t.Mode == "id_watermark")
            {
                param = Convert.ToInt64(Db.Scalar(local, "SELECT ISNULL(MAX(ID),0) FROM dbo.[" + t.Dest + "] WHERE StoreName = @s", null, Db.P("@s", store)));
                hasParam = true;
            }
            else if (t.Mode == "si_window")
            {
                long maxPs = Convert.ToInt64(Db.Scalar(local, "SELECT ISNULL(MAX(ID),0) FROM dbo.ProductSaleInformation WHERE StoreName = @s", null, Db.P("@s", store)));
                param = Math.Max(0, maxPs - 1000);
                hasParam = true;
            }

            // destination metadata
            var destCols = Db.Query(local, @"SELECT c.name FROM sys.columns c WHERE c.object_id = OBJECT_ID(@t) ORDER BY c.column_id", null, Db.P("@t", "dbo." + t.Dest))
                             .Rows.Cast<DataRow>().Select(r => (string)r[0]).ToList();
            if (destCols.Count == 0) throw new InvalidOperationException("destination table dbo." + t.Dest + " not found");
            var pkCols = Db.Query(local, @"SELECT c.name FROM sys.indexes i JOIN sys.index_columns ic ON ic.object_id=i.object_id AND ic.index_id=i.index_id
                                          JOIN sys.columns c ON c.object_id=ic.object_id AND c.column_id=ic.column_id
                                          WHERE i.object_id = OBJECT_ID(@t) AND i.is_primary_key = 1 ORDER BY ic.key_ordinal", null, Db.P("@t", "dbo." + t.Dest))
                             .Rows.Cast<DataRow>().Select(r => (string)r[0]).ToList();
            if (pkCols.Count == 0) throw new InvalidOperationException("dbo." + t.Dest + " has no primary key; refusing to merge");
            var destSet = new HashSet<string>(destCols, StringComparer.OrdinalIgnoreCase);
            bool hasSync = destSet.Contains("Sync"), hasSyncDt = destSet.Contains("SyncDateTime");

            using (var cmd = new SqlCommand(t.Query, pos))
            {
                cmd.CommandTimeout = 600;
                if (hasParam) cmd.Parameters.AddWithValue("@Param1", param);
                using (var rdr = cmd.ExecuteReader())
                {
                    // source columns that exist in destination (case-insensitive), mapped to destination spelling
                    var map = new List<KeyValuePair<int, string>>();
                    for (int i = 0; i < rdr.FieldCount; i++)
                    {
                        string d = destCols.FirstOrDefault(x => string.Equals(x, rdr.GetName(i), StringComparison.OrdinalIgnoreCase));
                        if (d != null && !string.Equals(d, "StoreName", StringComparison.OrdinalIgnoreCase)) map.Add(new KeyValuePair<int, string>(i, d));
                    }
                    string storeCol = destCols.First(x => string.Equals(x, "StoreName", StringComparison.OrdinalIgnoreCase));
                    var stageCols = map.Select(m => m.Value).ToList();
                    stageCols.Add(storeCol);
                    if (hasSync) stageCols.Add(destCols.First(x => x.Equals("Sync", StringComparison.OrdinalIgnoreCase)));
                    if (hasSyncDt) stageCols.Add(destCols.First(x => x.Equals("SyncDateTime", StringComparison.OrdinalIgnoreCase)));
                    foreach (var k in pkCols)
                        if (!stageCols.Contains(k, StringComparer.OrdinalIgnoreCase))
                            throw new InvalidOperationException("source query for " + t.Name + " lacks key column " + k);

                    string colList = string.Join(",", stageCols.Select(Q));
                    Db.Exec(local, "IF OBJECT_ID('tempdb..#stage') IS NOT NULL DROP TABLE #stage; SELECT TOP 0 " + colList + " INTO #stage FROM dbo.[" + t.Dest + "];");

                    var buffer = new DataTable();
                    foreach (var sc in stageCols) buffer.Columns.Add(sc, typeof(object));
                    DateTime now = DateTime.Now;
                    while (true)
                    {
                        buffer.Rows.Clear();
                        while (buffer.Rows.Count < _c.pos_batch_rows && rdr.Read())
                        {
                            var row = buffer.NewRow();
                            for (int j = 0; j < map.Count; j++) row[j] = rdr.GetValue(map[j].Key);
                            int n = map.Count;
                            row[n++] = store;
                            if (hasSync) row[n++] = 0;
                            if (hasSyncDt) row[n++] = now;
                            buffer.Rows.Add(row);
                        }
                        if (buffer.Rows.Count == 0) break;
                        examined += buffer.Rows.Count;
                        changed += MergeBatch(local, t.Dest, buffer, stageCols, pkCols);
                        Log.Debug("POS", t.Name + " batch rows=" + buffer.Rows.Count + " total=" + examined);
                    }
                    Db.Exec(local, "DROP TABLE #stage;");
                }
            }
            if (hasParam) return param.ToString();
            return "full";
        }

        int MergeBatch(SqlConnection local, string dest, DataTable buffer, List<string> cols, List<string> keys)
        {
            using (var tx = local.BeginTransaction())
            {
                Db.Exec(local, "TRUNCATE TABLE #stage;", tx);
                using (var bulk = new SqlBulkCopy(local, SqlBulkCopyOptions.Default, tx))
                {
                    bulk.DestinationTableName = "#stage";
                    bulk.BulkCopyTimeout = 600;
                    foreach (var c in cols) bulk.ColumnMappings.Add(c, c);
                    bulk.WriteToServer(buffer);
                }
                // de-duplicate on key (source DISTINCT/joins can repeat a key; MERGE would fail)
                Db.Exec(local, ";WITH d AS (SELECT ROW_NUMBER() OVER (PARTITION BY " + string.Join(",", keys.Select(Q)) + " ORDER BY (SELECT 0)) rn FROM #stage) DELETE FROM d WHERE rn > 1;", tx);

                var valueCols = cols.Where(c => !keys.Contains(c, StringComparer.OrdinalIgnoreCase)).ToList();
                var compareCols = valueCols.Where(c => !c.Equals("Sync", StringComparison.OrdinalIgnoreCase) && !c.Equals("SyncDateTime", StringComparison.OrdinalIgnoreCase)).ToList();
                var sb = new StringBuilder();
                sb.Append("MERGE dbo.[" + dest + "] WITH (HOLDLOCK) AS T USING #stage AS S ON ");
                sb.Append(string.Join(" AND ", keys.Select(k => "T." + Q(k) + " = S." + Q(k))));
                if (valueCols.Count > 0)
                {
                    sb.Append(" WHEN MATCHED");
                    if (compareCols.Count > 0)
                        sb.Append(" AND EXISTS (SELECT " + string.Join(",", compareCols.Select(c => "S." + Q(c))) + " EXCEPT SELECT " + string.Join(",", compareCols.Select(c => "T." + Q(c))) + ")");
                    sb.Append(" THEN UPDATE SET " + string.Join(",", valueCols.Select(c => "T." + Q(c) + " = S." + Q(c))));
                }
                sb.Append(" WHEN NOT MATCHED BY TARGET THEN INSERT (" + string.Join(",", cols.Select(Q)) + ") VALUES (" + string.Join(",", cols.Select(c => "S." + Q(c))) + ");");
                int n = Db.Exec(local, sb.ToString(), tx);
                tx.Commit();
                return n;
            }
        }

        static string Q(string ident) { return "[" + ident.Replace("]", "]]") + "]"; }

        /// <summary>Last sale bill / last GRN exactly as VB UpdateOrderHeaderDetails reads them from the POS.</summary>
        public void ReadHeaderFacts(out string lastSaleBillNo, out DateTime? lastBillDateTime, out long? lastGrn)
        {
            lastSaleBillNo = null; lastBillDateTime = null; lastGrn = null;
            using (var pos = Db.OpenPos(_c))
            {
                using (var cmd = new SqlCommand("SELECT TOP 1 Transactiondate, BNumber FROM ProductSaleInformation WHERE BNumber LIKE 'C%' ORDER BY Transactiondate DESC, BNumber DESC", pos))
                using (var r = cmd.ExecuteReader())
                    if (r.Read())
                    {
                        lastSaleBillNo = r["BNumber"].ToString();
                        if (!(r["Transactiondate"] is DBNull)) lastBillDateTime = Convert.ToDateTime(r["Transactiondate"]);
                    }
                var g = Db.Scalar(pos, "SELECT TOP 1 Grnnumber FROM Purchasetrans where InvoiceSeries = 'IV' ORDER BY Grndate DESC");
                if (g != null && g != DBNull.Value) lastGrn = Convert.ToInt64(g);
            }
        }
    }
}
