using System;
using System.Collections.Generic;
using System.Data;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.ServiceProcess;
using System.Threading;

namespace NMVSyncAgent
{
    /// <summary>A named job with its own interval and failure backoff.</summary>
    public class Job
    {
        public string Name; public JobConfig Cfg; public Action Body; public Backoff Backoff;
        public DateTime NextRunUtc = DateTime.UtcNow;
    }

    /// <summary>Two worker lanes: network (orders/results/heartbeat) and local (POS sync/housekeeping),
    /// so a long POS bootstrap never delays order results.</summary>
    public class Scheduler
    {
        readonly AgentConfig _c;
        readonly ManualResetEvent _stop = new ManualResetEvent(false);
        readonly List<Thread> _threads = new List<Thread>();

        public Scheduler(AgentConfig c) { _c = c; }

        public static Dictionary<string, Action> BuildJobs(AgentConfig c)
        {
            var ho = new HoClient(c); var pos = new PosSync(c);
            var pull = new OrderPull(c, ho, pos); var push = new ResultPush(c, ho);
            return new Dictionary<string, Action>
            {
                { "results_push",    push.Run },
                { "orders_pull",     pull.Run },
                { "heartbeat",       () => Heartbeat(c, ho, push) },
                { "pos_incremental", () => { if (c.pos_enabled && !pos.RunCategory("pos_incremental", pos.IncrementalTables())) throw new Exception("one or more POS tables failed"); } },
                { "pos_master",      () => { if (c.pos_enabled && !pos.RunCategory("pos_master", pos.MasterTables())) throw new Exception("one or more POS tables failed"); } },
                { "housekeeping",    () => Housekeeping(c) },
            };
        }

        public void Start()
        {
            var bodies = BuildJobs(_c);
            var network = new[] { "results_push", "orders_pull", "heartbeat" };
            var localLane = new[] { "pos_incremental", "pos_master", "housekeeping" };
            StartLane("net", network, bodies);
            StartLane("local", localLane, bodies);
        }

        void StartLane(string lane, string[] names, Dictionary<string, Action> bodies)
        {
            var jobs = names.Where(n => _c.Job(n).enabled).Select(n => new Job
            {
                Name = n, Cfg = _c.Job(n), Body = bodies[n], Backoff = new Backoff(30, _c.max_backoff_sec),
            }).ToList();
            foreach (var j in jobs) Log.Info("AGENT", "job " + j.Name + " enabled interval=" + j.Cfg.interval_sec + "s lane=" + lane);
            var t = new Thread(() => Loop(jobs)) { IsBackground = true, Name = "lane-" + lane };
            _threads.Add(t); t.Start();
        }

        void Loop(List<Job> jobs)
        {
            while (!_stop.WaitOne(1000))
            {
                foreach (var j in jobs)
                {
                    if (_stop.WaitOne(0)) return;
                    if (DateTime.UtcNow < j.NextRunUtc || !j.Backoff.Ready) continue;
                    var sw = Stopwatch.StartNew();
                    try
                    {
                        j.Body();
                        if (j.Backoff.Failures > 0) Log.Info("AGENT", j.Name + " recovered after " + j.Backoff.Failures + " failure(s)");
                        j.Backoff.Success();
                    }
                    catch (HoException hex)
                    {
                        bool auth = hex.Response != null && hex.Response.Outcome == HoOutcome.Auth;
                        int wait = j.Backoff.Fail(auth);
                        Log.Warn(auth ? "AUTH" : "RETRY", j.Name + " failed (" + hex.Message + ") attempt=" + j.Backoff.Failures + " next in " + wait + "s");
                    }
                    catch (Exception ex)
                    {
                        int wait = j.Backoff.Fail();
                        Log.Error("RETRY", j.Name + " failed attempt=" + j.Backoff.Failures + " next in " + wait + "s", ex);
                    }
                    j.NextRunUtc = DateTime.UtcNow.AddSeconds(j.Cfg.interval_sec);
                    Log.Debug("AGENT", j.Name + " took " + sw.ElapsedMilliseconds + "ms");
                }
            }
        }

        public void Stop()
        {
            _stop.Set();
            foreach (var t in _threads) t.Join(TimeSpan.FromSeconds(25));
        }

        // ---------------------------------------------------------------- heartbeat / housekeeping
        static void Heartbeat(AgentConfig c, HoClient ho, ResultPush push)
        {
            using (var local = Db.OpenLocal(c))
            {
                int pending = push.QueueDepth(local);
                int rejected = Convert.ToInt32(Db.Scalar(local, "SELECT COUNT(*) FROM dbo.nmv_change_queue WHERE sync_state='REJECTED'"));
                Log.Info("HEARTBEAT", "queue pending=" + pending + " rejected=" + rejected + " ho=" + (ho.Configured ? "enabled" : "disabled"));
                if (!ho.Configured) return;
                var oldest = Db.Scalar(local, "SELECT MIN(captured_at) FROM dbo.nmv_change_queue WHERE sync_state='PENDING'");
                var res = ho.Post("agent/heartbeat", new
                {
                    device_id = SecretStore.Get("ho_device_id"), agent_version = HoClient.AgentVersion,
                    queue = new { pending = pending, rejected = rejected, oldest_pending_at = oldest is DBNull ? null : ((DateTimeOffset)oldest).ToString("o") },
                    last_success = new
                    {
                        orders_pull = Db.GetState(local, "last_ok:orders_pull"), results_push = Db.GetState(local, "last_ok:results_push"),
                        pos_master = Db.GetState(local, "pos_last_ok:Products"), pos_incremental = Db.GetState(local, "pos_last_ok:ProductSaleInformation"),
                    },
                    current_order_id = Db.GetState(local, "current_order_id"),
                }, "hb-" + Guid.NewGuid());
                if (res.Outcome != HoOutcome.Ok) throw new HoException(res);
            }
        }

        static void Housekeeping(AgentConfig c)
        {
            using (var local = Db.OpenLocal(c))
            {
                int q = Db.Exec(local, "DELETE FROM dbo.nmv_change_queue WHERE sync_state='ACKED' AND acked_at < DATEADD(DAY, -@d, SYSDATETIMEOFFSET())", null, Db.P("@d", c.acked_retention_days));
                int a = Db.Exec(local, "DELETE FROM dbo.nmv_sync_audit WHERE at < DATEADD(DAY, -@d, SYSDATETIMEOFFSET())", null, Db.P("@d", c.audit_retention_days));
                Log.Info("HOUSEKEEP", "purged acked_changes=" + q + " audit_rows=" + a);
            }
            Log.Purge(c.log_retention_days);
        }
    }

    public class AgentService : ServiceBase
    {
        Scheduler _s;
        public AgentService() { ServiceName = "NMVSyncAgent"; CanStop = true; CanShutdown = true; }
        protected override void OnStart(string[] args)
        {
            AgentConfig c = AgentConfig.Load();
            Log.Level = c.log_level;
            Log.Info("AGENT", "==== service start v" + HoClient.AgentVersion + " store=" + c.store_code + " local=" + c.local_server + "/" + c.local_database
                     + " pos=" + (c.pos_enabled ? c.pos_server + "/" + c.pos_database + " (" + c.pos_credential_source + ")" : "disabled")
                     + " ho=" + (c.ho_enabled ? c.ho_base_url : "disabled") + " ====");
            if (c.ho_enabled && c.allow_insecure_http) Log.Warn("AGENT", "allow_insecure_http is ON — traffic to HO is not encrypted. Test use only.");
            _s = new Scheduler(c); _s.Start();
        }
        protected override void OnStop() { RequestAdditionalTime(30000); Log.Info("AGENT", "service stopping"); if (_s != null) _s.Stop(); Log.Info("AGENT", "service stopped"); }
        protected override void OnShutdown() { OnStop(); }
    }
}
