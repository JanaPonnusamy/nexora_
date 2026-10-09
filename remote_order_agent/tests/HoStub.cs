// TEST-ONLY HO stub implementing docs/02_HO_API_Contract.md on http://localhost:<port>/api/nmv/v1/
// Usage: HoStub.exe <port> <scenario> <stateDir>
// Scenarios: normal | lost_response | partial | corrupt | wrong_store | auth401 | bad_ack | order_v2
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

class HoStub
{
    const string StoreId = "4A2CEFF0-13C5-484C-B263-DE297E1E23E3";
    const string Token = "test-device-token-0001", Secret = "test-device-secret-0001";
    static string Scenario, StateDir;
    static int lostOnce = 0;

    static void Main(string[] a)
    {
        int port = int.Parse(a[0]); Scenario = a[1]; StateDir = a[2];
        Directory.CreateDirectory(StateDir);
        var l = new HttpListener(); l.Prefixes.Add("http://localhost:" + port + "/"); l.Start();
        Console.WriteLine("stub listening scenario=" + Scenario);
        while (true)
        {
            var ctx = l.GetContext();
            try { Handle(ctx); } catch (Exception ex) { Reply(ctx, 500, new { ok = false, error = new { code = "STUB", message = ex.Message } }); }
        }
    }

    static JObject Env(object extra)
    {
        var o = JObject.FromObject(extra);
        o["ok"] = true; o["store_code"] = Scenario == "wrong_store" ? "NMX" : "NMV"; o["store_id"] = StoreId;
        return o;
    }

    static void Handle(HttpListenerContext ctx)
    {
        var req = ctx.Request;
        string body; using (var sr = new StreamReader(req.InputStream, Encoding.UTF8)) body = sr.ReadToEnd();
        string path = req.Url.AbsolutePath.Replace("/api/nmv/v1", "");
        Log(req.HttpMethod + " " + path + " idem=" + req.Headers["Idempotency-Key"]);
        if (req.Headers["X-Nexora-Store-Code"] != "NMV" || req.Headers["X-Nexora-Store-Id"] != StoreId) { Reply(ctx, 403, new { ok = false }); return; }

        if (path == "/agent/register")
        {
            var b = JObject.Parse(body);
            if ((string)b["enrollment_code"] != "ENROLL-TEST-1") { Reply(ctx, 401, new { ok = false }); return; }
            Reply(ctx, 200, Env(new { device_id = "dev-1", device_token = Token, device_secret = Secret }));
            return;
        }
        if (Scenario == "auth401") { Reply(ctx, 401, new { ok = false, error = new { code = "AUTH", message = "revoked" } }); return; }
        // verify bearer + HMAC signature
        string ts = req.Headers["X-Nexora-Timestamp"];
        string canonical = ts + "\n" + req.HttpMethod + "\n" + req.Url.PathAndQuery + "\n" + Sha(Encoding.UTF8.GetBytes(body));
        if (req.Headers["Authorization"] != "Bearer " + Token || req.Headers["X-Nexora-Signature"] != Hmac(Secret, canonical))
        { Log("SIGNATURE FAIL"); Reply(ctx, 401, new { ok = false }); return; }
        if (Math.Abs((DateTime.UtcNow - new DateTime(1970, 1, 1)).TotalSeconds - long.Parse(ts)) > 300) { Reply(ctx, 401, new { ok = false }); return; }

        if (path == "/agent/heartbeat") { File.WriteAllText(Path.Combine(StateDir, "last_heartbeat.json"), body); Reply(ctx, 200, Env(new { server_time = DateTimeOffset.Now })); return; }

        if (path == "/orders/pending")
        {
            var order = JObject.Parse(File.ReadAllText(Path.Combine(StateDir, "order.json")));
            if (Scenario == "order_v2") { order["version"] = 2; }
            if (Scenario == "corrupt") { ((JArray)order["lines"])[0]["order_qty"] = (int)((JArray)order["lines"])[0]["order_qty"] + 5; }
            Reply(ctx, 200, Env(new { orders = new[] { order } }));
            return;
        }
        if (path.StartsWith("/orders/") && path.EndsWith("/ack"))
        {
            var b = JObject.Parse(body);
            File.AppendAllText(Path.Combine(StateDir, "acks.log"), b.ToString(Formatting.None) + Environment.NewLine);
            Reply(ctx, 200, Env(new { order_id = (long)b["order_id"], version = (int)b["version"], state = (string)b["state"] }));
            return;
        }
        if (path == "/order-results")
        {
            var b = JObject.Parse(body);
            string seenFile = Path.Combine(StateDir, "seen_changes.txt");
            var seen = new HashSet<long>(File.Exists(seenFile) ? File.ReadAllLines(seenFile).Select(long.Parse) : new long[0]);
            var ids = ((JArray)b["items"]).Select(x => (long)x["change_id"]).ToList();
            var accepted = new List<long>(); var dups = new List<long>(); var rejected = new List<object>();
            for (int i = 0; i < ids.Count; i++)
            {
                long id = ids[i];
                if (Scenario == "partial" && i == 0 && !seen.Contains(id)) { rejected.Add(new { change_id = id, code = "UNKNOWN_ORDER", message = "test final reject", retryable = false }); continue; }
                if (seen.Contains(id)) dups.Add(id); else { accepted.Add(id); seen.Add(id); }
            }
            File.WriteAllLines(seenFile, seen.Select(x => x.ToString()));
            File.AppendAllText(Path.Combine(StateDir, "results.log"), b.ToString(Formatting.None) + Environment.NewLine);
            if (Scenario == "lost_response" && lostOnce++ == 0) { Log("simulating lost response after commit"); Reply(ctx, 502, new { ok = false }); return; }
            if (Scenario == "bad_ack") { Reply(ctx, 200, Env(new { batch_id = (string)b["batch_id"], items_sha256 = (string)b["items_sha256"], accepted = accepted.Take(1), duplicates = new long[0], rejected = new object[0] })); return; }
            Reply(ctx, 200, Env(new { batch_id = (string)b["batch_id"], items_sha256 = (string)b["items_sha256"], accepted = accepted, duplicates = dups, rejected = rejected }));
            return;
        }
        Reply(ctx, 404, new { ok = false });
    }

    static void Reply(HttpListenerContext ctx, int status, object o)
    {
        var bytes = Encoding.UTF8.GetBytes(JsonConvert.SerializeObject(o));
        ctx.Response.StatusCode = status; ctx.Response.ContentType = "application/json";
        ctx.Response.OutputStream.Write(bytes, 0, bytes.Length); ctx.Response.Close();
    }
    static void Log(string s) { Console.WriteLine(DateTime.Now.ToString("HH:mm:ss ") + s); File.AppendAllText(Path.Combine(StateDir, "stub.log"), DateTime.Now.ToString("HH:mm:ss ") + s + Environment.NewLine); }
    static string Sha(byte[] b) { using (var s = SHA256.Create()) return string.Concat(s.ComputeHash(b).Select(x => x.ToString("x2"))); }
    static string Hmac(string k, string d) { using (var h = new HMACSHA256(Encoding.UTF8.GetBytes(k))) return string.Concat(h.ComputeHash(Encoding.UTF8.GetBytes(d)).Select(x => x.ToString("x2"))); }
}
