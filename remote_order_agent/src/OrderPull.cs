using System;
using System.Collections.Generic;
using System.Data;
using System.Data.SqlClient;
using System.Diagnostics;
using System.Globalization;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace NMVSyncAgent
{
    public class OrderLine
    {
        public long ProductCode; public string ProductName;
        public double? TotalStock, SaleUnit, PurchasePrice, Mrp, SlsQty, MaxSaleQty, MinQty, MaxQty, Frequence;
        public string SubLocation, UnitDescription, WantedType, ProductTypeName, Remarks;
        public DateTime? LastReceivedDate, LastSaleDate, TransactionDate, WantedDate;
        public int Status, OrderQty, OrgOrderQty, ProductType;
    }

    public class HoOrder
    {
        public long OrderId; public int Version; public string StoreCode; public int? OrderNo;
        public DateTime OrderDateTime; public int? MinDays, MaxDays;
        public string LastSaleBillNo; public DateTime? LastBillDateTime; public long? LastGrn;
        public int LineCount; public string LinesSha256;
        public List<OrderLine> Lines = new List<OrderLine>();
    }

    public class OrderValidationException : Exception
    {
        public string Code;
        public OrderValidationException(string code, string msg) : base(msg) { Code = code; }
    }

    /// <summary>HO → local OrderManagement/OrderHeaderDetails. Idempotent; one SQL transaction per order.</summary>
    public class OrderPull
    {
        readonly AgentConfig _c; readonly HoClient _ho; readonly PosSync _pos;
        public OrderPull(AgentConfig c, HoClient ho, PosSync pos) { _c = c; _ho = ho; _pos = pos; }

        // ------------------------------------------------------------ parsing & validation
        public static HoOrder Parse(JObject o, string expectedStore)
        {
            var h = new HoOrder();
            try
            {
                h.OrderId = (long)o["order_id"];
                h.Version = (int)o["version"];
                h.StoreCode = (string)o["store_code"];
                h.OrderNo = (int?)o["order_no"];
                h.OrderDateTime = ParseDate(o["order_datetime"], "order_datetime").Value;
                h.MinDays = (int?)o["min_days"]; h.MaxDays = (int?)o["max_days"];
                h.LastSaleBillNo = (string)o["last_sale_bill_no"];
                h.LastBillDateTime = ParseDate(o["last_bill_datetime"], null);
                h.LastGrn = (long?)o["last_grn"];
                h.LineCount = (int)o["line_count"];
                h.LinesSha256 = ((string)o["lines_sha256"] ?? "").ToLowerInvariant();
            }
            catch (OrderValidationException) { throw; }
            catch (Exception ex) { throw new OrderValidationException("INVALID_LINE", "header field invalid: " + ex.Message); }

            if (h.StoreCode != expectedStore) throw new OrderValidationException("WRONG_STORE", "order store_code=" + h.StoreCode);
            if (h.OrderId <= 0 || h.Version <= 0) throw new OrderValidationException("INVALID_LINE", "order_id/version must be positive");
            var arr = o["lines"] as JArray;
            if (arr == null) throw new OrderValidationException("INVALID_LINE", "lines missing");
            if (arr.Count != h.LineCount) throw new OrderValidationException("COUNT_MISMATCH", "line_count=" + h.LineCount + " received=" + arr.Count);

            int idx = 0;
            foreach (JObject l in arr)
            {
                idx++;
                try
                {
                    var x = new OrderLine
                    {
                        ProductCode = (long)l["product_code"],
                        ProductName = (string)l["product_name"],
                        TotalStock = (double?)l["total_stock"], SaleUnit = (double?)l["sale_unit"],
                        PurchasePrice = (double?)l["purchase_price"], Mrp = (double?)l["mrp"],
                        SubLocation = (string)l["sub_location"], UnitDescription = (string)l["unit_description"],
                        LastReceivedDate = ParseDate(l["last_received_date"], null), LastSaleDate = ParseDate(l["last_sale_date"], null),
                        TransactionDate = ParseDate(l["transaction_date"], null), WantedDate = ParseDate(l["wanted_date"], null),
                        SlsQty = (double?)l["sls_qty"], MaxSaleQty = (double?)l["max_sale_qty"],
                        WantedType = (string)l["wanted_type"],
                        Status = IntStrict(l["status"], "status"),
                        OrderQty = IntStrict(l["order_qty"], "order_qty"),
                        ProductType = IntStrict(l["product_type"], "product_type"),
                        ProductTypeName = (string)l["product_type_name"],
                        MinQty = (double?)l["min_qty"], MaxQty = (double?)l["max_qty"], Frequence = (double?)l["frequence"],
                        Remarks = (string)l["remarks"],
                    };
                    x.OrgOrderQty = l["org_order_qty"] == null || l["org_order_qty"].Type == JTokenType.Null ? x.OrderQty : IntStrict(l["org_order_qty"], "org_order_qty");
                    if (x.ProductCode <= 0) throw new Exception("product_code must be positive");
                    if (string.IsNullOrWhiteSpace(x.ProductName)) throw new Exception("product_name required");
                    if (x.Status != 0 && x.Status != 2) throw new Exception("status must be 0 or 2");
                    if (x.OrderQty < 0 || x.OrgOrderQty < 0) throw new Exception("quantities must be >= 0");
                    if (x.ProductType != 0 && x.ProductType != 1) throw new Exception("product_type must be 0 or 1");
                    string expectName = x.ProductType == 0 ? "Non Pharma" : "Pharma";
                    if (x.ProductTypeName != expectName) throw new Exception("product_type_name must be '" + expectName + "'");
                    if (string.IsNullOrWhiteSpace(x.WantedType)) throw new Exception("wanted_type required");
                    if (x.ProductName.Length > 200 || (x.WantedType ?? "").Length > 200 || (x.Remarks ?? "").Length > 200
                        || (x.SubLocation ?? "").Length > 200 || (x.UnitDescription ?? "").Length > 200) throw new Exception("text longer than 200");
                    h.Lines.Add(x);
                }
                catch (Exception ex) { throw new OrderValidationException("INVALID_LINE", "line " + idx + ": " + ex.Message); }
            }
            var dup = h.Lines.GroupBy(x => x.ProductCode).FirstOrDefault(g => g.Count() > 1);
            if (dup != null) throw new OrderValidationException("DUPLICATE_PRODUCT", "product_code " + dup.Key + " repeated");

            string hash = LinesHash(h.Lines);
            if (hash != h.LinesSha256) throw new OrderValidationException("HASH_MISMATCH", "computed " + hash + " != " + h.LinesSha256);
            return h;
        }

        public static string LinesHash(IEnumerable<OrderLine> lines)
        {
            var canon = lines.OrderBy(x => x.ProductCode)
                             .Select(x => string.Join("|", x.ProductCode.ToString(CultureInfo.InvariantCulture), x.OrderQty.ToString(CultureInfo.InvariantCulture),
                                                     x.OrgOrderQty.ToString(CultureInfo.InvariantCulture), x.Status.ToString(CultureInfo.InvariantCulture),
                                                     x.ProductType.ToString(CultureInfo.InvariantCulture)));
            return Hash.Sha256Hex(string.Join("\n", canon));
        }

        static int IntStrict(JToken t, string name)
        {
            if (t == null || t.Type != JTokenType.Integer) throw new Exception(name + " must be an integer");
            return (int)t;
        }

        static DateTime? ParseDate(JToken t, string requiredName)
        {
            if (t == null || t.Type == JTokenType.Null)
            {
                if (requiredName != null) throw new OrderValidationException("INVALID_LINE", requiredName + " required");
                return null;
            }
            if (t.Type == JTokenType.Date)
            {
                var v = t.ToObject<DateTimeOffset>();
                return v.LocalDateTime;
            }
            return DateTimeOffset.Parse((string)t, CultureInfo.InvariantCulture).LocalDateTime;
        }

        // ------------------------------------------------------------ job
        public void Run()
        {
            if (!_ho.Configured) { Log.Debug("ORDER", "HO not configured/enabled; skip"); return; }
            using (var local = Db.OpenLocal(_c))
            {
                RetryPendingAcks(local);
                var res = _ho.Get("orders/pending?limit=" + _c.order_pull_limit);
                if (res.Outcome != HoOutcome.Ok) throw new HoException(res);
                var orders = res.Body["orders"] as JArray;
                if (orders == null) throw new HoException(new HoResponse { Outcome = HoOutcome.Transient, Error = "orders array missing" });
                Log.Info("ORDER", "pull: " + orders.Count + " pending order(s) from HO");
                foreach (JObject o in orders) Process(local, o);
                Db.SetState(local, "last_ok:orders_pull", DateTimeOffset.Now.ToString("o"));
            }
        }

        void Process(SqlConnection local, JObject raw)
        {
            var sw = Stopwatch.StartNew();
            long orderId = 0; int version = 0;
            try { orderId = (long)raw["order_id"]; version = (int)raw["version"]; } catch { }
            HoOrder order;
            try { order = Parse(raw, _c.store_code); }
            catch (OrderValidationException vex)
            {
                Log.Warn("ORDER", "order " + orderId + " v" + version + " REJECTED " + vex.Code + ": " + vex.Message);
                RecordAndAck(local, orderId, version, Hash.Sha256Hex(raw.ToString(Newtonsoft.Json.Formatting.None)), 0, "REJECTED", vex.Code, vex.Message);
                Db.Audit(local, "orders_pull", orderId.ToString(), "VALIDATE", null, null, "REJECTED", sw.ElapsedMilliseconds, vex.Code + " " + vex.Message);
                return;
            }

            // idempotency: already handled this exact version?
            var prior = Db.Query(local, "SELECT state, payload_sha256, ack_state FROM dbo.nmv_order_inbox WHERE order_id=@o AND version=@v", null,
                                 Db.P("@o", order.OrderId), Db.P("@v", order.Version));
            if (prior.Rows.Count == 1 && (string)prior.Rows[0]["state"] != "DEFERRED")
            {
                if ((string)prior.Rows[0]["payload_sha256"] != order.LinesSha256)
                {
                    Log.Warn("ORDER", "order " + order.OrderId + " v" + order.Version + " re-sent with different payload — ID_CONFLICT");
                    Ack(local, order.OrderId, order.Version, order.LinesSha256, 0, "REJECTED", "ID_CONFLICT", "same order_id/version, different payload");
                }
                else
                {
                    Log.Info("ORDER", "order " + order.OrderId + " v" + order.Version + " already " + prior.Rows[0]["state"] + " — re-acknowledging (duplicate download)");
                    Ack(local, order.OrderId, order.Version, order.LinesSha256, order.LineCount, (string)prior.Rows[0]["state"], null, null);
                }
                return;
            }

            // legacy id collision (exists locally but was never delivered by HO)
            int legacy = Convert.ToInt32(Db.Scalar(local, @"SELECT (SELECT COUNT(*) FROM dbo.OrderHeaderDetails WHERE OrderId=@o)
                + (SELECT COUNT(*) FROM dbo.OrderManagementBackup WHERE OrderId=@o AND StoreName=@s)
                - (SELECT COUNT(*) FROM dbo.nmv_order_inbox WHERE order_id=@o AND state='APPLIED')", null, Db.P("@o", order.OrderId), Db.P("@s", _c.store_name)));
            bool isAmendment = Convert.ToInt32(Db.Scalar(local, "SELECT COUNT(*) FROM dbo.nmv_order_inbox WHERE order_id=@o AND state='APPLIED'", null, Db.P("@o", order.OrderId))) > 0;
            if (legacy > 0 && !isAmendment)
            {
                RecordAndAck(local, order.OrderId, order.Version, order.LinesSha256, 0, "REJECTED", "ID_CONFLICT", "order_id already used locally by a non-HO order");
                return;
            }

            // unknown products
            var unknown = UnknownProducts(local, order);
            if (unknown.Count > 0)
            {
                string msg = unknown.Count + " product(s) not in local Products for " + _c.store_name + " e.g. " + string.Join(",", unknown.Take(10));
                if (_c.unknown_product_policy == "reject")
                {
                    RecordAndAck(local, order.OrderId, order.Version, order.LinesSha256, 0, "REJECTED", "UNKNOWN_PRODUCTS", msg);
                    return;
                }
                Log.Warn("ORDER", "order " + order.OrderId + ": " + msg + " (policy=warn, applying)");
            }

            // replacement safety
            string deferReason;
            if (isAmendment)
            {
                int edits = Convert.ToInt32(Db.Scalar(local, "SELECT COUNT(*) FROM dbo.nmv_change_queue WHERE order_id=@o", null, Db.P("@o", order.OrderId)));
                if (edits > 0)
                {
                    RecordAndAck(local, order.OrderId, order.Version, order.LinesSha256, 0, "REJECTED", "USER_EDITS_EXIST", edits + " user change(s) already captured for this order");
                    return;
                }
            }
            else if (!SafeToReplace(local, out deferReason))
            {
                Log.Info("ORDER", "order " + order.OrderId + " DEFERRED: " + deferReason);
                RecordAndAck(local, order.OrderId, order.Version, order.LinesSha256, 0, "DEFERRED", "PREVIOUS_ORDER_ACTIVE", deferReason);
                return;
            }

            // header facts from POS when HO did not send them (same queries as VB)
            if (order.LastSaleBillNo == null || order.LastGrn == null)
            {
                try
                {
                    string bill; DateTime? billDt; long? grn;
                    _pos.ReadHeaderFacts(out bill, out billDt, out grn);
                    if (order.LastSaleBillNo == null) { order.LastSaleBillNo = bill; order.LastBillDateTime = order.LastBillDateTime ?? billDt; }
                    if (order.LastGrn == null) order.LastGrn = grn;
                }
                catch (Exception ex) { Log.Warn("ORDER", "POS unavailable for header facts (LastSaleBillNo/LastGRN left NULL): " + ex.Message); }
            }

            int applied = Apply(local, order, isAmendment);
            Log.Info("ORDER", "order " + order.OrderId + " v" + order.Version + " APPLIED lines=" + applied + (isAmendment ? " (amendment)" : "") + " dur=" + sw.ElapsedMilliseconds + "ms");
            Db.Audit(local, "orders_pull", order.OrderId.ToString(), isAmendment ? "AMEND" : "APPLY", order.LineCount, applied, "OK", sw.ElapsedMilliseconds, "v" + order.Version);
            Ack(local, order.OrderId, order.Version, order.LinesSha256, applied, "APPLIED", null, null);
        }

        List<long> UnknownProducts(SqlConnection local, HoOrder o)
        {
            var known = new HashSet<long>();
            foreach (var chunk in o.Lines.Select(x => x.ProductCode).Distinct().Select((v, i) => new { v, i }).GroupBy(x => x.i / 900))
            {
                string inList = string.Join(",", chunk.Select(x => x.v.ToString(CultureInfo.InvariantCulture)));   // integers only (validated)
                foreach (DataRow r in Db.Query(local, "SELECT ProductCode FROM dbo.Products WHERE StoreName=@s AND ProductCode IN (" + inList + ")", null, Db.P("@s", _c.store_name)).Rows)
                    known.Add(Convert.ToInt64(r[0]));
            }
            return o.Lines.Select(x => x.ProductCode).Where(p => !known.Contains(p)).ToList();
        }

        public bool SafeToReplace(SqlConnection local, out string reason)
        {
            reason = null;
            int pending = Convert.ToInt32(Db.Scalar(local, "SELECT COUNT(*) FROM dbo.nmv_change_queue WHERE store_name=@s AND sync_state='PENDING'", null, Db.P("@s", _c.store_name)));
            if (pending > 0) { reason = pending + " user change(s) of the current order not yet acknowledged by HO"; return false; }
            var last = Db.Scalar(local, "SELECT MAX(captured_at) FROM dbo.nmv_change_queue WHERE store_name=@s", null, Db.P("@s", _c.store_name));
            if (last != null && last != DBNull.Value)
            {
                var age = DateTimeOffset.Now - (DateTimeOffset)last;
                if (age.TotalMinutes < _c.order_replace_quiet_minutes)
                {
                    reason = "user edited the current order " + (int)age.TotalMinutes + " min ago (quiet period " + _c.order_replace_quiet_minutes + " min)";
                    return false;
                }
            }
            return true;
        }

        // ------------------------------------------------------------ apply (single transaction)
        static readonly string[] OmCols = { "ProductCode","ProductName","TotalStock","SaleUnit","PurchasePrice","MRP","SubLocation","UnitDescription",
            "LastReceivedDate","LastSaleDate","SLSQty","WantedDate","WantedType","Status","MaxSaleQty","OrderQty","OrgOrderQty","ProductType",
            "ProductTypeName","Remarks","OrderId","MinQty","MaxQty","Frequence","StoreName","StoreCode","Transactiondate","Qtycheck" };

        // positional OrderManagement → OrderManagementBackup copy (identical to VB 'INSERT … SELECT *', guarded for PK/NOT NULL)
        const string ArchiveSql = @"
INSERT INTO dbo.OrderManagementBackup
SELECT om.ProductCode, om.ProductName, om.TotalStock, om.SaleUnit, om.PurchasePrice, om.MRP, om.SubLocation, om.UnitDescription,
       om.LastReceivedDate, om.LastSaleDate, om.CMS, om.LMS, om.SLSQty, om.WantedDate, om.WantedType, om.Status, om.MaxSaleQty,
       om.OrderQty, om.OrgOrderQty, om.OrQty, om.OrSupplier, om.OrSupplierCode, om.LastGRN, om.LastGRNQTY, om.ProductType,
       om.ProductTypeName, om.Remarks, om.OrderId, om.MinQty, om.MaxQty, om.Frequence, om.StoreName, om.StoreCode,
       ISNULL(om.Transactiondate, om.WantedDate), ISNULL(om.Qtycheck, 0), om.Free
FROM dbo.OrderManagement om
WHERE om.StoreName = @s AND om.ProductCode IS NOT NULL AND om.OrderId IS NOT NULL
  AND (om.Transactiondate IS NOT NULL OR om.WantedDate IS NOT NULL)
  AND NOT EXISTS (SELECT 1 FROM dbo.OrderManagementBackup b WHERE b.StoreName = om.StoreName AND b.OrderId = om.OrderId AND b.ProductCode = om.ProductCode);";

        int Apply(SqlConnection local, HoOrder o, bool amendment)
        {
            var dt = new DataTable();
            foreach (var c in OmCols) dt.Columns.Add(c, typeof(object));
            foreach (var x in o.Lines)
            {
                DateTime wanted = x.WantedDate ?? o.OrderDateTime;
                dt.Rows.Add((double)x.ProductCode, x.ProductName, N(x.TotalStock), N(x.SaleUnit), N(x.PurchasePrice), N(x.Mrp),
                    S(x.SubLocation), S(x.UnitDescription), D(x.LastReceivedDate), D(x.LastSaleDate), N(x.SlsQty), wanted, x.WantedType,
                    x.Status.ToString(CultureInfo.InvariantCulture), N(x.MaxSaleQty), (double)x.OrderQty, (double)x.OrgOrderQty,
                    (double)x.ProductType, x.ProductTypeName, S(x.Remarks), o.OrderId, N(x.MinQty), N(x.MaxQty), N(x.Frequence),
                    _c.store_name, _c.store_code_numeric, (object)x.TransactionDate ?? wanted, 0);
            }

            using (var tx = local.BeginTransaction(IsolationLevel.Serializable))
            {
                Db.Exec(local, "SET XACT_ABORT ON;", tx);
                int archived = 0, deleted;
                if (amendment)
                {
                    deleted = Db.Exec(local, "DELETE FROM dbo.OrderManagement WHERE StoreName=@s AND OrderId=@o", tx, Db.P("@s", _c.store_name), Db.P("@o", o.OrderId));
                }
                else
                {
                    archived = Db.Exec(local, ArchiveSql, tx, Db.P("@s", _c.store_name));
                    deleted = Db.Exec(local, "DELETE FROM dbo.OrderManagement WHERE StoreName=@s", tx, Db.P("@s", _c.store_name));
                }
                using (var bulk = new SqlBulkCopy(local, SqlBulkCopyOptions.CheckConstraints, tx))
                {
                    bulk.DestinationTableName = "dbo.OrderManagement";
                    foreach (var c in OmCols) bulk.ColumnMappings.Add(c, c);
                    bulk.WriteToServer(dt);
                }
                Db.Exec(local, @"IF NOT EXISTS (SELECT 1 FROM dbo.OrderHeaderDetails WHERE OrderId=@o)
                    INSERT INTO dbo.OrderHeaderDetails (StoreName, OrderId, OrderNo, OrderDateTime, LastSaleBillNo, LastBillDateTime, LastGRN, MinDays, MaxDays)
                    VALUES (@s, @o, @no, @dt, @bill, @billdt, @grn, @min, @max)", tx,
                    Db.P("@s", _c.store_name), Db.P("@o", o.OrderId),
                    Db.P("@no", o.OrderNo ?? NextOrderNo(local, tx, o.OrderDateTime)), Db.P("@dt", o.OrderDateTime),
                    Db.P("@bill", o.LastSaleBillNo), Db.P("@billdt", o.LastBillDateTime), Db.P("@grn", o.LastGrn),
                    Db.P("@min", o.MinDays), Db.P("@max", o.MaxDays));

                // integrity checks before commit
                int present = Convert.ToInt32(Db.Scalar(local, "SELECT COUNT(*) FROM dbo.OrderManagement WHERE StoreName=@s AND OrderId=@o", tx, Db.P("@s", _c.store_name), Db.P("@o", o.OrderId)));
                if (present != o.LineCount) throw new InvalidOperationException("post-apply count " + present + " != " + o.LineCount);
                int dups = Convert.ToInt32(Db.Scalar(local, "SELECT COUNT(*) FROM (SELECT ProductCode FROM dbo.OrderManagement WHERE StoreName=@s GROUP BY ProductCode HAVING COUNT(*)>1) d", tx, Db.P("@s", _c.store_name)));
                if (dups > 0) throw new InvalidOperationException(dups + " duplicate ProductCode(s) in OrderManagement after apply");

                Db.Exec(local, @"DELETE FROM dbo.nmv_order_inbox WHERE order_id=@o AND version=@v AND state='DEFERRED';
                    INSERT INTO dbo.nmv_order_inbox (order_id, version, payload_sha256, line_count, state, applied_at)
                    VALUES (@o, @v, @h, @n, 'APPLIED', SYSDATETIMEOFFSET());", tx,
                    Db.P("@o", o.OrderId), Db.P("@v", o.Version), Db.P("@h", o.LinesSha256), Db.P("@n", o.LineCount));
                Db.SetState(local, "current_order_id", o.OrderId.ToString(CultureInfo.InvariantCulture), tx);
                tx.Commit();
                Log.Info("ORDER", "order " + o.OrderId + ": archived=" + archived + " removed=" + deleted + " inserted=" + present);
                return present;
            }
        }

        static int NextOrderNo(SqlConnection local, SqlTransaction tx, DateTime when)
        {
            // same rule as VB UpdateOrderHeaderDetails: count of today's headers + 1
            return 1 + Convert.ToInt32(Db.Scalar(local, "SELECT COUNT(*) FROM dbo.OrderHeaderDetails WHERE StoreName='NMV' AND CONVERT(date, OrderDateTime) = @d", tx, Db.P("@d", when.Date)));
        }

        static object N(double? v) { return v.HasValue ? (object)v.Value : DBNull.Value; }
        static object S(string v) { return v == null ? (object)DBNull.Value : v; }
        static object D(DateTime? v) { return v.HasValue ? (object)v.Value : DBNull.Value; }

        // ------------------------------------------------------------ acknowledgements
        void RecordAndAck(SqlConnection local, long orderId, int version, string hash, int lines, string state, string code, string reason)
        {
            if (orderId > 0 && version > 0)
            {
                Db.Exec(local, @"MERGE dbo.nmv_order_inbox AS t USING (SELECT @o AS order_id, @v AS version) AS s
                      ON t.order_id = s.order_id AND t.version = s.version
                    WHEN MATCHED AND t.state <> 'APPLIED' THEN UPDATE SET state=@st, payload_sha256=@h, reason_code=@rc, reason=@r, ack_state='PENDING'
                    WHEN NOT MATCHED THEN INSERT (order_id, version, payload_sha256, line_count, state, reason_code, reason)
                         VALUES (@o, @v, @h, @n, @st, @rc, @r);", null,
                    Db.P("@o", orderId), Db.P("@v", version), Db.P("@h", (hash ?? "").PadRight(64).Substring(0, 64)), Db.P("@n", lines),
                    Db.P("@st", state), Db.P("@rc", code), Db.P("@r", reason));
            }
            Ack(local, orderId, version, hash, lines, state, code, reason);
        }

        void Ack(SqlConnection local, long orderId, int version, string hash, int lines, string state, string code, string reason)
        {
            if (orderId <= 0 || version <= 0) { Log.Warn("ORDER", "cannot acknowledge order without valid id/version"); return; }
            var res = _ho.Post("orders/" + orderId + "/ack", new
            {
                order_id = orderId, version = version, state = state, payload_sha256 = hash, applied_line_count = lines,
                reason_code = code, reason = reason, applied_at = DateTimeOffset.Now.ToString("o")
            }, "ack-" + orderId + "-" + version + "-" + state);

            bool echoed = res.Outcome == HoOutcome.Ok && (long?)res.Body["order_id"] == orderId && (int?)res.Body["version"] == version && (string)res.Body["state"] == state;
            Db.Exec(local, @"UPDATE dbo.nmv_order_inbox SET ack_attempts = ack_attempts + 1,
                    ack_state = CASE WHEN @ok = 1 THEN 'ACKED' ELSE 'PENDING' END,
                    acked_at = CASE WHEN @ok = 1 THEN SYSDATETIMEOFFSET() ELSE acked_at END, last_error = @e
                    WHERE order_id=@o AND version=@v", null,
                Db.P("@ok", echoed ? 1 : 0), Db.P("@e", echoed ? null : (res.Error ?? "ack response did not echo order/version/state")),
                Db.P("@o", orderId), Db.P("@v", version));
            if (echoed) Log.Info("ACK", "order " + orderId + " v" + version + " " + state + " acknowledged by HO");
            else Log.Warn("ACK", "order " + orderId + " v" + version + " " + state + " ack not confirmed: " + (res.Error ?? "echo mismatch") + " — will retry");
        }

        void RetryPendingAcks(SqlConnection local)
        {
            var rows = Db.Query(local, "SELECT TOP 20 order_id, version, payload_sha256, line_count, state, reason_code, reason FROM dbo.nmv_order_inbox WHERE ack_state='PENDING' AND state <> 'DEFERRED' ORDER BY received_at");
            foreach (DataRow r in rows.Rows)
                Ack(local, (long)r["order_id"], (int)r["version"], ((string)r["payload_sha256"]).Trim(), (int)r["line_count"], (string)r["state"],
                    r["reason_code"] as string, r["reason"] as string);
        }
    }

    public class HoException : Exception
    {
        public HoResponse Response;
        public HoException(HoResponse r) : base(r.Error) { Response = r; }
    }
}
