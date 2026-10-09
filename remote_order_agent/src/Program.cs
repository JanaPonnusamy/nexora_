using System;
using System.Data;
using System.Linq;
using System.ServiceProcess;
using System.Threading;

namespace NMVSyncAgent
{
    public static class Program
    {
        // Exit codes: 0 ok, 1 error, 2 verification failed
        [STAThread]
        public static int Main(string[] args)
        {
            if (args.Length == 0 && !Environment.UserInteractive)
            {
                ServiceBase.Run(new AgentService());
                return 0;
            }
            Log.Console_ = true;
            string cmd = args.Length > 0 ? args[0].ToLowerInvariant() : "--help";
            try
            {
                switch (cmd)
                {
                    case "--console": return RunConsole();
                    case "--once": return RunOnce(args.Length > 1 ? args[1] : null);
                    case "--verify": return Verify(AgentConfig.Load()) ? 0 : 2;
                    case "--status": return Status(AgentConfig.Load());
                    case "--set-secret": return SetSecret(args.Length > 1 ? args[1] : null);
                    case "--enroll": return Enroll();
                    case "--settings":
                        System.Windows.Forms.Application.EnableVisualStyles();
                        System.Windows.Forms.Application.Run(new SettingsForm());
                        return 0;
                    default:
                        Console.WriteLine(@"NMVSyncAgent " + HoClient.AgentVersion + @"
  (no args, as service)    run as Windows service NMVSyncAgent
  --console                run all jobs in this console (Ctrl+C to stop)
  --once <job>             run one job: results_push | orders_pull | heartbeat | pos_incremental | pos_master | housekeeping
  --verify                 integrity checks (schema, trigger, keys, duplicates, references, config, secrets)
  --status                 queue / inbox / last-run summary
  --set-secret <name>      read a secret value from stdin and store it with DPAPI (names: pos_password)
  --enroll                 read the HO one-time enrollment code from stdin and enroll this device
  --settings               open the Settings window (HO link, enable HO sync, test, enroll, restart service)
Config: " + AgentPaths.ConfigFile);
                        return cmd == "--help" ? 0 : 1;
                }
            }
            catch (Exception ex)
            {
                Log.Error("AGENT", "command " + cmd + " failed", ex);
                return 1;
            }
        }

        static int RunConsole()
        {
            var svc = new Scheduler(AgentConfig.Load());
            var done = new ManualResetEvent(false);
            Console.CancelKeyPress += (s, e) => { e.Cancel = true; done.Set(); };
            Log.Info("AGENT", "console mode start");
            svc.Start();
            done.WaitOne();
            svc.Stop();
            return 0;
        }

        static int RunOnce(string job)
        {
            var c = AgentConfig.Load(); Log.Level = c.log_level;
            var jobs = Scheduler.BuildJobs(c);
            Action a;
            if (job == null || !jobs.TryGetValue(job, out a)) { Console.WriteLine("unknown job: " + job); return 1; }
            Log.Info("AGENT", "--once " + job);
            a();
            return 0;
        }

        static int SetSecret(string name)
        {
            if (name != "pos_password") { Console.WriteLine("allowed names: pos_password (HO credentials are set by --enroll)"); return 1; }
            string v = Console.In.ReadLine();
            if (string.IsNullOrEmpty(v)) { Console.WriteLine("empty value; nothing stored"); return 1; }
            SecretStore.Set(name, v);
            Log.Info("CONFIG", "secret '" + name + "' stored (DPAPI LocalMachine)");
            return 0;
        }

        static int Enroll()
        {
            var c = AgentConfig.Load();
            if (!c.ho_enabled) { Console.WriteLine("ho_enabled is false in agent.json"); return 1; }
            string code = Console.In.ReadLine();
            if (string.IsNullOrWhiteSpace(code)) { Console.WriteLine("no enrollment code on stdin"); return 1; }
            new HoClient(c).Enroll(code.Trim());
            return 0;
        }

        static int Status(AgentConfig c)
        {
            using (var l = Db.OpenLocal(c))
            {
                foreach (DataRow r in Db.Query(l, "SELECT sync_state, COUNT(*) n, MIN(change_id) min_id, MAX(change_id) max_id FROM dbo.nmv_change_queue GROUP BY sync_state").Rows)
                    Console.WriteLine("queue  {0,-9} count={1} ids={2}..{3}", r[0], r[1], r[2], r[3]);
                foreach (DataRow r in Db.Query(l, "SELECT TOP 5 order_id, version, state, ack_state, reason_code, received_at FROM dbo.nmv_order_inbox ORDER BY received_at DESC").Rows)
                    Console.WriteLine("inbox  order={0} v{1} {2} ack={3} {4} {5}", r[0], r[1], r[2], r[3], r[4], r[5]);
                foreach (DataRow r in Db.Query(l, "SELECT state_key, state_value, updated_at FROM dbo.nmv_sync_state ORDER BY state_key").Rows)
                    Console.WriteLine("state  {0} = {1}", r[0], r[1]);
            }
            return 0;
        }

        // ------------------------------------------------------------ integrity verification
        public static bool Verify(AgentConfig c)
        {
            bool ok = true;
            Action<bool, string> check = (pass, what) => { Console.WriteLine((pass ? "  PASS  " : "  FAIL  ") + what); if (!pass) ok = false; };
            Action<string> info = s => Console.WriteLine("  INFO  " + s);
            Console.WriteLine("Config: " + AgentPaths.ConfigFile);
            check(c.store_code == "NMV", "store_code is NMV");
            check(!c.ho_enabled || c.ho_base_url.StartsWith("https://", StringComparison.OrdinalIgnoreCase) || c.allow_insecure_http, "HO URL is HTTPS (or HO disabled)");
            if (c.allow_insecure_http) info("allow_insecure_http=true (test only)");
            info("secrets present: " + string.Join(", ", SecretStore.Names()));
            using (var l = Db.OpenLocal(c))
            {
                foreach (var t in new[] { "nmv_integration_store", "nmv_change_queue", "nmv_order_inbox", "nmv_sync_state", "nmv_sync_audit" })
                    check(Db.Scalar(l, "SELECT OBJECT_ID(@t,'U')", null, Db.P("@t", "dbo." + t)) != DBNull.Value, "table " + t + " exists");
                var trg = Db.Scalar(l, "SELECT OBJECTPROPERTY(OBJECT_ID('dbo.trg_nmv_OrderManagement_track'),'ExecIsTriggerDisabled')");
                check(trg != DBNull.Value && Convert.ToInt32(trg) == 0, "change-capture trigger present and enabled");
                check(Convert.ToInt32(Db.Scalar(l, "SELECT COUNT(*) FROM dbo.nmv_integration_store WHERE StoreName=@s AND IsManaged=1", null, Db.P("@s", c.store_name))) == 1, "store " + c.store_name + " is integration-managed");
                check(!string.IsNullOrEmpty(Db.GetState(l, "queue_epoch")), "queue_epoch present");
                check(Convert.ToInt32(Db.Scalar(l, "SELECT COUNT(*) FROM sys.columns WHERE object_id=OBJECT_ID('dbo.OrderManagement')")) ==
                      Convert.ToInt32(Db.Scalar(l, "SELECT COUNT(*) FROM sys.columns WHERE object_id=OBJECT_ID('dbo.OrderManagementBackup')")),
                      "OrderManagement / OrderManagementBackup column counts equal (INSERT…SELECT * compatible)");
                int dupOm = Convert.ToInt32(Db.Scalar(l, "SELECT COUNT(*) FROM (SELECT ProductCode FROM dbo.OrderManagement WHERE StoreName=@s GROUP BY ProductCode HAVING COUNT(*)>1) d", null, Db.P("@s", c.store_name)));
                check(dupOm == 0, "no duplicate ProductCode in OrderManagement for " + c.store_name + " (found " + dupOm + ")");
                int nullIds = Convert.ToInt32(Db.Scalar(l, "SELECT COUNT(*) FROM dbo.OrderManagement WHERE StoreName=@s AND (OrderId IS NULL OR ProductCode IS NULL)", null, Db.P("@s", c.store_name)));
                check(nullIds == 0, "no OrderManagement rows with NULL OrderId/ProductCode (found " + nullIds + ")");
                var orders = Db.Query(l, "SELECT OrderId, COUNT(*) n FROM dbo.OrderManagement WHERE StoreName=@s GROUP BY OrderId", null, Db.P("@s", c.store_name));
                info("current OrderManagement orders: " + string.Join(", ", orders.Rows.Cast<DataRow>().Select(r => r[0] + " (" + r[1] + " lines)")));
                int noHeader = Convert.ToInt32(Db.Scalar(l, "SELECT COUNT(DISTINCT om.OrderId) FROM dbo.OrderManagement om WHERE om.StoreName=@s AND NOT EXISTS (SELECT 1 FROM dbo.OrderHeaderDetails h WHERE h.OrderId=om.OrderId)", null, Db.P("@s", c.store_name)));
                check(noHeader == 0, "every current order has an OrderHeaderDetails row (missing " + noHeader + ")");
                int orphan = Convert.ToInt32(Db.Scalar(l, "SELECT COUNT(*) FROM dbo.OrderManagement om WHERE om.StoreName=@s AND NOT EXISTS (SELECT 1 FROM dbo.Products p WHERE p.StoreName=om.StoreName AND p.ProductCode=om.ProductCode)", null, Db.P("@s", c.store_name)));
                if (orphan == 0) check(true, "all OrderManagement products exist in Products"); else info(orphan + " OrderManagement product(s) not found in Products (detail panels will be empty for them)");
                foreach (var t in new[] { "Products", "ProductSaleInformation", "SaleInformation", "ProductTrans", "PurchaseTrans", "SalesRep", "Batches", "SupplierProductMatch", "OrderSuppliers" })
                {
                    var rows = Db.Scalar(l, "SELECT SUM(p.rows) FROM sys.partitions p WHERE p.object_id=OBJECT_ID(@t) AND p.index_id IN (0,1)", null, Db.P("@t", "dbo." + t));
                    var pk = Db.Scalar(l, "SELECT COUNT(*) FROM sys.indexes WHERE object_id=OBJECT_ID(@t) AND is_primary_key=1", null, Db.P("@t", "dbo." + t));
                    check(Convert.ToInt32(pk) == 1, t + " has a primary key (duplicate keys impossible); rows=" + rows + "; last POS sync=" + (Db.GetState(l, "pos_last_ok:" + t) ?? "never by agent"));
                }
                foreach (DataRow r in Db.Query(l, "SELECT sync_state, COUNT(*) FROM dbo.nmv_change_queue GROUP BY sync_state").Rows) info("queue " + r[0] + " = " + r[1]);
            }
            if (c.pos_enabled)
            {
                try { using (var p = Db.OpenPos(c)) check(true, "POS reachable: " + p.DataSource + "/" + p.Database); }
                catch (Exception ex) { check(false, "POS reachable (" + ex.Message + ")"); }
            }
            Console.WriteLine(ok ? "VERIFY OK" : "VERIFY FAILED");
            return ok;
        }
    }
}
