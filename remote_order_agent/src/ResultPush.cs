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
    /// <summary>
    /// nmv_change_queue → HO. Always sends the head of the queue (lowest PENDING change_ids) so HO receives
    /// changes in order. Only ids HO explicitly accepted/duplicated become ACKED; non-retryable rejections become
    /// REJECTED (kept); anything unaccounted for stays PENDING and is retried with the same idempotency keys.
    /// </summary>
    public class ResultPush
    {
        readonly AgentConfig _c; readonly HoClient _ho;
        public ResultPush(AgentConfig c, HoClient ho) { _c = c; _ho = ho; }

        public int QueueDepth(SqlConnection local)
        {
            return Convert.ToInt32(Db.Scalar(local, "SELECT COUNT(*) FROM dbo.nmv_change_queue WHERE sync_state='PENDING'"));
        }

        /// <summary>Runs until the queue is drained or a batch fails. Throws HoException on transport/auth failure.</summary>
        public void Run()
        {
            if (!_ho.Configured)
            {
                using (var l = Db.OpenLocal(_c)) Log.Debug("PUSH", "HO not configured/enabled; queue pending=" + QueueDepth(l));
                return;
            }
            using (var local = Db.OpenLocal(_c))
            {
                string epoch = Db.GetState(local, "queue_epoch");
                if (string.IsNullOrEmpty(epoch)) throw new InvalidOperationException("queue_epoch missing (schema not installed?)");
                int depth = QueueDepth(local);
                if (depth == 0) { Log.Debug("PUSH", "queue empty"); return; }
                Log.Info("PUSH", "start queue_pending=" + depth);
                int totalAcked = 0;
                for (int round = 0; round < 50; round++)
                {
                    var rows = Db.Query(local, "SELECT TOP (@n) * FROM dbo.nmv_change_queue WHERE sync_state='PENDING' ORDER BY change_id", null, Db.P("@n", _c.push_batch_size));
                    if (rows.Rows.Count == 0) break;
                    int acked = SendBatch(local, epoch, rows);
                    totalAcked += acked;
                    if (acked == 0) break;   // nothing progressed — wait for next cycle
                }
                Db.SetState(local, "last_ok:results_push", DateTimeOffset.Now.ToString("o"));
                Log.Info("PUSH", "end acked=" + totalAcked + " queue_pending=" + QueueDepth(local));
            }
        }

        int SendBatch(SqlConnection local, string epoch, DataTable rows)
        {
            var sw = Stopwatch.StartNew();
            var ids = rows.Rows.Cast<DataRow>().Select(r => (long)r["change_id"]).OrderBy(x => x).ToList();
            string idList = string.Join(",", ids.Select(x => x.ToString(CultureInfo.InvariantCulture)));
            string itemsSha = Hash.Sha256Hex(idList);
            Guid batchId = Hash.DeterministicGuid(epoch + ":" + idList);   // same set ⇒ same batch id on retry

            var items = rows.Rows.Cast<DataRow>().Select(r => new
            {
                change_id = (long)r["change_id"],
                operation = (string)r["operation"],
                captured_at = ((DateTimeOffset)r["captured_at"]).ToString("o"),
                order_id = r["order_id"] as long?,
                product_code = r["product_code"] is DBNull ? (long?)null : Convert.ToInt64(r["product_code"]),
                before = Snapshot(r, "old_"),
                after = Snapshot(r, "new_"),
                db_login = r["db_login"] as string, host_name = r["host_name"] as string, app_name = r["app_name"] as string,
            }).ToList();

            Db.Exec(local, "UPDATE dbo.nmv_change_queue SET attempts = attempts + 1, last_attempt_at = SYSDATETIMEOFFSET(), batch_id = @b WHERE change_id IN (" + idList + ")",
                    null, Db.P("@b", batchId));
            Log.Info("PUSH", "batch " + batchId + " items=" + ids.Count + " ids=" + ids.First() + ".." + ids.Last());

            var res = _ho.Post("order-results", new { batch_id = batchId, queue_epoch = epoch, count = ids.Count, items_sha256 = itemsSha, items = items }, batchId.ToString());
            if (res.Outcome != HoOutcome.Ok)
            {
                MarkError(local, idList, res.Error);
                Db.Audit(local, "results_push", batchId.ToString(), "POST", ids.Count, 0, "FAILED", sw.ElapsedMilliseconds, res.Error);
                throw new HoException(res);
            }

            // ---- validate the acknowledgement; never trust status 200 alone
            var b = res.Body;
            string problem = null;
            if (!string.Equals((string)b["batch_id"], batchId.ToString(), StringComparison.OrdinalIgnoreCase)) problem = "batch_id not echoed";
            else if ((string)b["items_sha256"] != itemsSha) problem = "items_sha256 not echoed";
            var accepted = Ids(b["accepted"]); var dups = Ids(b["duplicates"]);
            var rejected = (b["rejected"] as JArray ?? new JArray()).OfType<JObject>().ToList();
            var rejectedIds = rejected.Select(x => (long?)x["change_id"] ?? -1).ToList();
            var all = accepted.Concat(dups).Concat(rejectedIds).ToList();
            if (problem == null && all.Count != all.Distinct().Count()) problem = "an id appears in more than one result list";
            if (problem == null && (all.Count != ids.Count || all.Except(ids).Any())) problem = "acknowledged ids do not match the ids sent";
            if (problem != null)
            {
                MarkError(local, idList, "invalid ack: " + problem);
                Db.Audit(local, "results_push", batchId.ToString(), "VALIDATE", ids.Count, 0, "FAILED", sw.ElapsedMilliseconds, problem);
                throw new HoException(new HoResponse { Outcome = HoOutcome.Transient, Error = "invalid acknowledgement: " + problem });
            }

            using (var tx = local.BeginTransaction())
            {
                var ok = accepted.Concat(dups).ToList();
                if (ok.Count > 0)
                    Db.Exec(local, "UPDATE dbo.nmv_change_queue SET sync_state='ACKED', acked_at=SYSDATETIMEOFFSET(), last_error=NULL WHERE sync_state='PENDING' AND change_id IN ("
                                   + string.Join(",", ok) + ")", tx);
                foreach (var rj in rejected)
                {
                    bool retryable = rj["retryable"] != null && rj["retryable"].Type == JTokenType.Boolean && (bool)rj["retryable"];
                    string msg = ((string)rj["code"] ?? "") + " " + ((string)rj["message"] ?? "");
                    Db.Exec(local, "UPDATE dbo.nmv_change_queue SET sync_state = CASE WHEN @r = 1 THEN 'PENDING' ELSE 'REJECTED' END, last_error=@e WHERE change_id=@id", tx,
                            Db.P("@r", retryable ? 1 : 0), Db.P("@e", msg.Trim()), Db.P("@id", (long)rj["change_id"]));
                    Log.Warn("PUSH", "change " + (long)rj["change_id"] + " rejected by HO (" + (retryable ? "retryable" : "final") + "): " + msg.Trim());
                }
                tx.Commit();
            }
            int finalRejected = rejected.Count(x => !(x["retryable"] != null && x["retryable"].Type == JTokenType.Boolean && (bool)x["retryable"]));
            Log.Info("ACK", "batch " + batchId + " accepted=" + accepted.Count + " duplicates=" + dups.Count + " rejected=" + rejected.Count + " dur=" + sw.ElapsedMilliseconds + "ms");
            Db.Audit(local, "results_push", batchId.ToString(), "ACK", ids.Count, accepted.Count + dups.Count,
                     rejected.Count == 0 ? "OK" : "REJECTED", sw.ElapsedMilliseconds, "dup=" + dups.Count + " rej=" + rejected.Count);
            // a retryable rejection at the head blocks progress this cycle (ordering); final rejections do not
            return accepted.Count + dups.Count + finalRejected;
        }

        static object Snapshot(DataRow r, string p)
        {
            return new
            {
                order_qty = r[p + "order_qty"] is DBNull ? (double?)null : (double)r[p + "order_qty"],
                or_qty = r[p + "or_qty"] is DBNull ? (double?)null : (double)r[p + "or_qty"],
                qtycheck = r[p + "qtycheck"] as int?,
                remarks = r[p + "remarks"] as string,
                or_supplier = r[p + "or_supplier"] as string,
                or_supplier_code = r[p + "or_supplier_code"] as string,
                status = r[p + "status"] as string,
            };
        }

        static List<long> Ids(JToken t)
        {
            var a = t as JArray;
            if (a == null) return new List<long>();
            return a.Select(x => (long)x).ToList();
        }

        static void MarkError(SqlConnection local, string idList, string err)
        {
            Db.Exec(local, "UPDATE dbo.nmv_change_queue SET last_error=@e WHERE change_id IN (" + idList + ")", null,
                    Db.P("@e", err == null ? null : (err.Length > 1000 ? err.Substring(0, 1000) : err)));
        }
    }
}
