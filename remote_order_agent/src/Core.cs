using System;
using System.Collections.Generic;
using System.Data;
using System.Data.SqlClient;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace NMVSyncAgent
{
    // ------------------------------------------------------------------ paths
    public static class AgentPaths
    {
        public static string Root
        {
            get
            {
                string over = Environment.GetEnvironmentVariable("NMV_AGENT_HOME");
                if (!string.IsNullOrEmpty(over)) return over;
                return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "NMVSyncAgent");
            }
        }
        public static string ConfigFile { get { return Path.Combine(Root, "agent.json"); } }
        public static string SecretsFile { get { return Path.Combine(Root, "secrets.dat"); } }
        public static string LogDir { get { return Path.Combine(Root, "logs"); } }
    }

    // ------------------------------------------------------------------ logging
    public static class Log
    {
        static readonly object Gate = new object();
        public static bool Console_ = false;
        public static string Level = "INFO";
        static readonly Regex[] Redactors =
        {
            new Regex(@"(?i)(password|pwd|secret|token|signature|authorization|enrollment_code)(\s*[""']?\s*[:=]\s*[""']?)([^\s;""',}]+)"),
            new Regex(@"(?i)(bearer\s+)\S+"),
        };

        public static string Redact(string s)
        {
            if (s == null) return s;
            foreach (var r in Redactors) s = r.Replace(s, m => m.Groups[1].Value + (m.Groups.Count > 3 ? m.Groups[2].Value : "") + "***");
            return s;
        }

        public static void Debug(string cat, string msg) { if (Level == "DEBUG") Write("DEBUG", cat, msg); }
        public static void Info(string cat, string msg) { Write("INFO", cat, msg); }
        public static void Warn(string cat, string msg) { Write("WARN", cat, msg); }
        public static void Error(string cat, string msg, Exception ex = null)
        {
            Write("ERROR", cat, ex == null ? msg : msg + " | " + ex.GetType().Name + ": " + ex.Message);
            if (ex != null && Level == "DEBUG") Write("DEBUG", cat, ex.ToString());
        }

        static void Write(string level, string cat, string msg)
        {
            string line = string.Format("{0:yyyy-MM-dd HH:mm:ss.fff zzz} {1,-5} [{2}] {3}", DateTimeOffset.Now, level, cat, Redact(msg));
            lock (Gate)
            {
                try
                {
                    Directory.CreateDirectory(AgentPaths.LogDir);
                    File.AppendAllText(Path.Combine(AgentPaths.LogDir, "agent-" + DateTime.Now.ToString("yyyyMMdd") + ".log"), line + Environment.NewLine, Encoding.UTF8);
                }
                catch { /* logging must never crash the agent */ }
                if (Console_) Console.WriteLine(line);
            }
        }

        public static void Purge(int retentionDays)
        {
            try
            {
                if (!Directory.Exists(AgentPaths.LogDir)) return;
                foreach (var f in Directory.GetFiles(AgentPaths.LogDir, "agent-*.log"))
                    if (File.GetLastWriteTime(f) < DateTime.Now.AddDays(-retentionDays)) File.Delete(f);
            }
            catch (Exception ex) { Error("HOUSEKEEP", "log purge failed", ex); }
        }
    }

    // ------------------------------------------------------------------ configuration
    public class JobConfig
    {
        public bool enabled = true;
        public int interval_sec = 60;
    }

    public class AgentConfig
    {
        public string store_code = "NMV";
        public string store_id = "";
        public string store_name = "NMV";
        public double store_code_numeric = 10;

        public string local_server = @"DESKTOP-2\SQLEXPRESSORDER";
        public string local_database = "OrderNMC";
        public string local_auth = "windows";              // windows only (no stored SQL password)

        public bool pos_enabled = true;
        public string pos_credential_source = "dpapi";     // dpapi | stores_table
        public string pos_server = "DESKTOP-CLG2ECP";
        public string pos_database = "Shopaid";
        public string pos_username = "";
        public int pos_batch_rows = 5000;
        public bool pos_sync_ordersuppliers = false;       // see docs: legacy VB merge into OrderSuppliers never succeeded

        public bool ho_enabled = false;                    // stays false until HO implements the contract
        public string ho_base_url = "";                    // HO host root, editable in the Settings window
        public string ho_api_prefix = "api/nmv/v1";        // contract path prefix appended to ho_base_url
        public bool allow_insecure_http = false;
        public int ho_connect_timeout_sec = 15;
        public int ho_read_timeout_sec = 60;

        public int push_batch_size = 200;
        public int max_backoff_sec = 900;
        public int order_pull_limit = 5;
        public int order_replace_quiet_minutes = 20;
        public string unknown_product_policy = "warn";     // warn | reject

        public int acked_retention_days = 30;
        public int audit_retention_days = 90;
        public int log_retention_days = 30;
        public string log_level = "INFO";

        public Dictionary<string, JobConfig> jobs = new Dictionary<string, JobConfig>
        {
            { "results_push",    new JobConfig { interval_sec = 30 } },
            { "orders_pull",     new JobConfig { interval_sec = 60 } },
            { "heartbeat",       new JobConfig { interval_sec = 300 } },
            { "pos_incremental", new JobConfig { interval_sec = 900 } },
            { "pos_master",      new JobConfig { interval_sec = 3600 } },
            { "housekeeping",    new JobConfig { interval_sec = 21600 } },
        };

        public static AgentConfig Load()
        {
            if (!File.Exists(AgentPaths.ConfigFile))
                throw new InvalidOperationException("Config not found: " + AgentPaths.ConfigFile);
            var cfg = JsonConvert.DeserializeObject<AgentConfig>(File.ReadAllText(AgentPaths.ConfigFile));
            cfg.Validate();
            return cfg;
        }

        public void Validate()
        {
            if (store_code != "NMV") throw new InvalidOperationException("This agent build only operates as store NMV (config store_code=" + store_code + ").");
            if (string.IsNullOrWhiteSpace(store_id)) throw new InvalidOperationException("store_id missing in config.");
            if (local_auth != "windows") throw new InvalidOperationException("local_auth must be 'windows'.");
            if (pos_credential_source != "dpapi" && pos_credential_source != "stores_table")
                throw new InvalidOperationException("pos_credential_source must be dpapi or stores_table.");
            if (unknown_product_policy != "warn" && unknown_product_policy != "reject")
                throw new InvalidOperationException("unknown_product_policy must be warn or reject.");
            if (ho_enabled)
            {
                Uri u;
                if (!Uri.TryCreate(ho_base_url, UriKind.Absolute, out u)) throw new InvalidOperationException("ho_base_url invalid.");
                if (u.Scheme != Uri.UriSchemeHttps && !allow_insecure_http)
                    throw new InvalidOperationException("ho_base_url must be HTTPS (set allow_insecure_http only for an isolated test).");
            }
            foreach (var kv in jobs) if (kv.Value.interval_sec < 5) throw new InvalidOperationException("job " + kv.Key + " interval too small.");
        }

        public void Save()
        {
            Validate();
            System.IO.Directory.CreateDirectory(AgentPaths.Root);
            string tmp = AgentPaths.ConfigFile + ".tmp";
            File.WriteAllText(tmp, JsonConvert.SerializeObject(this, Formatting.Indented), new UTF8Encoding(false));
            if (File.Exists(AgentPaths.ConfigFile)) File.Replace(tmp, AgentPaths.ConfigFile, AgentPaths.ConfigFile + ".bak");
            else File.Move(tmp, AgentPaths.ConfigFile);
        }

        public JobConfig Job(string name)
        {
            JobConfig j;
            return jobs.TryGetValue(name, out j) ? j : new JobConfig { enabled = false };
        }
    }

    // ------------------------------------------------------------------ DPAPI secrets
    public static class SecretStore
    {
        static readonly byte[] Entropy = Encoding.UTF8.GetBytes("NMVSyncAgent/secrets/v1");

        static Dictionary<string, string> ReadAll()
        {
            if (!File.Exists(AgentPaths.SecretsFile)) return new Dictionary<string, string>();
            return JsonConvert.DeserializeObject<Dictionary<string, string>>(File.ReadAllText(AgentPaths.SecretsFile))
                   ?? new Dictionary<string, string>();
        }

        public static string Get(string name)
        {
            string b64;
            if (!ReadAll().TryGetValue(name, out b64)) return null;
            var plain = ProtectedData.Unprotect(Convert.FromBase64String(b64), Entropy, DataProtectionScope.LocalMachine);
            return Encoding.UTF8.GetString(plain);
        }

        public static void Set(string name, string value)
        {
            Directory.CreateDirectory(AgentPaths.Root);
            var all = ReadAll();
            all[name] = Convert.ToBase64String(ProtectedData.Protect(Encoding.UTF8.GetBytes(value), Entropy, DataProtectionScope.LocalMachine));
            File.WriteAllText(AgentPaths.SecretsFile, JsonConvert.SerializeObject(all, Formatting.Indented));
        }

        public static IEnumerable<string> Names() { return ReadAll().Keys; }
    }

    // ------------------------------------------------------------------ SQL helpers
    public static class Db
    {
        // 'NMV_AGENT' — the change-capture trigger ignores sessions carrying this marker
        public const string AgentMarkerHex = "0x4E4D565F4147454E54";

        public static SqlConnection OpenLocal(AgentConfig c)
        {
            var b = new SqlConnectionStringBuilder
            {
                DataSource = c.local_server,
                InitialCatalog = c.local_database,
                IntegratedSecurity = true,
                ApplicationName = "NMVSyncAgent",
                ConnectTimeout = 15,
            };
            var conn = new SqlConnection(b.ConnectionString);
            conn.Open();
            using (var cmd = new SqlCommand("SET CONTEXT_INFO " + AgentMarkerHex + ";", conn)) cmd.ExecuteNonQuery();
            return conn;
        }

        public static SqlConnection OpenPos(AgentConfig c)
        {
            string server = c.pos_server, database = c.pos_database, user = c.pos_username, pwd = null;
            if (c.pos_credential_source == "stores_table")
            {
                // reuse the credential row the VB app already uses (stores.storename = NMV); never logged
                using (var lc = OpenLocal(c))
                using (var cmd = new SqlCommand("SELECT TOP 1 servername, [database], username, password FROM dbo.stores WHERE storename = @s AND isactive = 1", lc))
                {
                    cmd.Parameters.AddWithValue("@s", c.store_name);
                    using (var r = cmd.ExecuteReader())
                    {
                        if (!r.Read()) throw new InvalidOperationException("No active stores row for " + c.store_name);
                        server = r.GetString(0); database = r.GetString(1); user = r.GetString(2); pwd = r.GetString(3);
                    }
                }
            }
            else
            {
                pwd = SecretStore.Get("pos_password");
                if (pwd == null || string.IsNullOrEmpty(user))
                    throw new InvalidOperationException("POS credentials not configured (pos_username in agent.json + secret 'pos_password').");
            }
            var b = new SqlConnectionStringBuilder
            {
                DataSource = server, InitialCatalog = database, UserID = user, Password = pwd,
                ApplicationName = "NMVSyncAgent-POS", ConnectTimeout = 15,
            };
            var conn = new SqlConnection(b.ConnectionString);
            conn.Open();
            return conn;
        }

        public static object Scalar(SqlConnection conn, string sql, SqlTransaction tx = null, params SqlParameter[] ps)
        {
            using (var cmd = new SqlCommand(sql, conn, tx))
            {
                cmd.CommandTimeout = 120;
                if (ps != null) cmd.Parameters.AddRange(ps);
                return cmd.ExecuteScalar();
            }
        }

        public static int Exec(SqlConnection conn, string sql, SqlTransaction tx = null, params SqlParameter[] ps)
        {
            using (var cmd = new SqlCommand(sql, conn, tx))
            {
                cmd.CommandTimeout = 600;
                if (ps != null) cmd.Parameters.AddRange(ps);
                return cmd.ExecuteNonQuery();
            }
        }

        public static DataTable Query(SqlConnection conn, string sql, SqlTransaction tx = null, params SqlParameter[] ps)
        {
            using (var cmd = new SqlCommand(sql, conn, tx))
            {
                cmd.CommandTimeout = 120;
                if (ps != null) cmd.Parameters.AddRange(ps);
                var dt = new DataTable();
                using (var r = cmd.ExecuteReader()) dt.Load(r);
                return dt;
            }
        }

        public static SqlParameter P(string name, object value)
        {
            return new SqlParameter(name, value ?? DBNull.Value);
        }

        public static string GetState(SqlConnection conn, string key)
        {
            var v = Scalar(conn, "SELECT state_value FROM dbo.nmv_sync_state WHERE state_key = @k", null, P("@k", key));
            return v == null || v == DBNull.Value ? null : (string)v;
        }

        public static void SetState(SqlConnection conn, string key, string value, SqlTransaction tx = null)
        {
            Exec(conn, @"MERGE dbo.nmv_sync_state AS t USING (SELECT @k AS state_key) AS s ON t.state_key = s.state_key
                         WHEN MATCHED THEN UPDATE SET state_value = @v, updated_at = SYSDATETIMEOFFSET()
                         WHEN NOT MATCHED THEN INSERT (state_key, state_value) VALUES (@k, @v);", tx, P("@k", key), P("@v", value));
        }

        public static void Audit(SqlConnection conn, string category, string item, string action, int? examined, int? changed,
                                 string outcome, long durationMs, string detail)
        {
            try
            {
                Exec(conn, @"INSERT INTO dbo.nmv_sync_audit (category, item, action, rows_examined, rows_changed, outcome, duration_ms, detail)
                             VALUES (@c, @i, @a, @e, @ch, @o, @d, @dt)", null,
                     P("@c", category), P("@i", item), P("@a", action), P("@e", examined), P("@ch", changed),
                     P("@o", outcome), P("@d", (int)Math.Min(int.MaxValue, durationMs)),
                     P("@dt", detail == null ? null : Log.Redact(detail.Length > 2000 ? detail.Substring(0, 2000) : detail)));
            }
            catch (Exception ex) { Log.Error("AUDIT", "audit write failed", ex); }
        }
    }

    // ------------------------------------------------------------------ hashing
    public static class Hash
    {
        public static string Sha256Hex(string s) { return Sha256Hex(Encoding.UTF8.GetBytes(s ?? "")); }
        public static string Sha256Hex(byte[] b)
        {
            using (var sha = SHA256.Create()) return Hex(sha.ComputeHash(b));
        }
        public static string HmacSha256Hex(string key, string data)
        {
            using (var h = new HMACSHA256(Encoding.UTF8.GetBytes(key))) return Hex(h.ComputeHash(Encoding.UTF8.GetBytes(data)));
        }
        public static string Hex(byte[] b)
        {
            var sb = new StringBuilder(b.Length * 2);
            foreach (var x in b) sb.Append(x.ToString("x2"));
            return sb.ToString();
        }
        public static Guid DeterministicGuid(string s)
        {
            using (var md5 = MD5.Create()) return new Guid(md5.ComputeHash(Encoding.UTF8.GetBytes(s)));
        }
    }

    // ------------------------------------------------------------------ backoff
    public class Backoff
    {
        readonly int _baseSec, _maxSec;
        readonly Random _rnd = new Random();
        public int Failures { get; private set; }
        public DateTime NotBeforeUtc { get; private set; }
        public Backoff(int baseSec, int maxSec) { _baseSec = baseSec; _maxSec = maxSec; NotBeforeUtc = DateTime.MinValue; }
        public bool Ready { get { return DateTime.UtcNow >= NotBeforeUtc; } }
        public void Success() { Failures = 0; NotBeforeUtc = DateTime.MinValue; }
        public int Fail(bool longWait = false)
        {
            Failures++;
            double secs = longWait ? _maxSec : Math.Min(_maxSec, _baseSec * Math.Pow(2, Math.Min(Failures - 1, 16)));
            secs = secs * (0.8 + 0.4 * _rnd.NextDouble());   // ±20 % jitter
            NotBeforeUtc = DateTime.UtcNow.AddSeconds(secs);
            return (int)secs;
        }
    }
}
