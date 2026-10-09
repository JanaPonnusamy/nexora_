using System;
using System.IO;
using System.Net;
using System.Text;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace NMVSyncAgent
{
    public enum HoOutcome { Ok, Transient, Auth, Rejected }

    public class HoResponse
    {
        public int Status;
        public HoOutcome Outcome;
        public JObject Body;
        public string Error;
    }

    /// <summary>HTTPS client for the NMV HO contract (docs/02_HO_API_Contract.md).</summary>
    public class HoClient
    {
        readonly AgentConfig _c;
        public const string AgentVersion = "1.0.0";

        public HoClient(AgentConfig c)
        {
            _c = c;
            ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;
            ServicePointManager.Expect100Continue = false;
        }

        public bool Configured
        {
            get { return _c.ho_enabled && SecretStore.Get("ho_device_token") != null && SecretStore.Get("ho_device_secret") != null; }
        }

        public HoResponse Get(string pathAndQuery) { return Send("GET", pathAndQuery, null, null, true); }
        public HoResponse Post(string pathAndQuery, object body, string idempotencyKey) { return Send("POST", pathAndQuery, body, idempotencyKey, true); }
        public HoResponse PostUnauthenticated(string pathAndQuery, object body) { return Send("POST", pathAndQuery, body, Guid.NewGuid().ToString(), false); }

        HoResponse Send(string method, string pathAndQuery, object body, string idemKey, bool signed)
        {
            var baseUri = new Uri(_c.ho_base_url.TrimEnd('/') + "/" + (_c.ho_api_prefix ?? "").Trim('/') + "/");
            if (baseUri.Scheme != Uri.UriSchemeHttps && !_c.allow_insecure_http)
                return new HoResponse { Outcome = HoOutcome.Rejected, Error = "HO URL is not HTTPS; refused" };
            var uri = new Uri(baseUri, pathAndQuery.TrimStart('/'));
            string json = body == null ? "" : JsonConvert.SerializeObject(body, Formatting.None);
            byte[] bytes = Encoding.UTF8.GetBytes(json);
            string requestId = Guid.NewGuid().ToString();

            var req = (HttpWebRequest)WebRequest.Create(uri);
            req.Method = method;
            req.Timeout = _c.ho_connect_timeout_sec * 1000;
            req.ReadWriteTimeout = _c.ho_read_timeout_sec * 1000;
            req.Accept = "application/json";
            req.UserAgent = "NMVSyncAgent/" + AgentVersion;
            req.Headers["X-Nexora-Store-Id"] = _c.store_id;
            req.Headers["X-Nexora-Store-Code"] = _c.store_code;
            req.Headers["X-Request-Id"] = requestId;
            if (idemKey != null) req.Headers["Idempotency-Key"] = idemKey;
            if (signed)
            {
                string token = SecretStore.Get("ho_device_token"), secret = SecretStore.Get("ho_device_secret");
                if (token == null || secret == null) return new HoResponse { Outcome = HoOutcome.Auth, Error = "device not enrolled" };
                string ts = ((long)(DateTime.UtcNow - new DateTime(1970, 1, 1)).TotalSeconds).ToString();
                string canonical = ts + "\n" + method + "\n" + uri.PathAndQuery + "\n" + Hash.Sha256Hex(bytes);
                req.Headers["Authorization"] = "Bearer " + token;
                req.Headers["X-Nexora-Timestamp"] = ts;
                req.Headers["X-Nexora-Signature"] = Hash.HmacSha256Hex(secret, canonical);
            }
            Log.Debug("HO", method + " " + uri.AbsolutePath + " req=" + requestId + " bytes=" + bytes.Length);

            int status = 0; string text = null;
            try
            {
                if (method != "GET")
                {
                    req.ContentType = "application/json; charset=utf-8";
                    req.ContentLength = bytes.Length;
                    using (var s = req.GetRequestStream()) s.Write(bytes, 0, bytes.Length);
                }
                using (var resp = (HttpWebResponse)req.GetResponse())
                {
                    status = (int)resp.StatusCode;
                    using (var sr = new StreamReader(resp.GetResponseStream(), Encoding.UTF8)) text = sr.ReadToEnd();
                }
            }
            catch (WebException wex)
            {
                var r = wex.Response as HttpWebResponse;
                if (r == null)
                    return new HoResponse { Outcome = HoOutcome.Transient, Error = "network: " + wex.Status + " " + wex.Message };
                status = (int)r.StatusCode;
                try { using (var sr = new StreamReader(r.GetResponseStream(), Encoding.UTF8)) text = sr.ReadToEnd(); } catch { }
                r.Close();
            }

            var res = new HoResponse { Status = status };
            if (status == 401 || status == 403) { res.Outcome = HoOutcome.Auth; res.Error = "HTTP " + status + " authentication/authorisation failed"; return res; }
            if (status == 408 || status == 429 || status >= 500) { res.Outcome = HoOutcome.Transient; res.Error = "HTTP " + status; return res; }

            try
            {
                res.Body = string.IsNullOrWhiteSpace(text) ? null
                    : JsonConvert.DeserializeObject<JObject>(text, new JsonSerializerSettings { DateParseHandling = DateParseHandling.None });
            }
            catch (Exception ex) { res.Outcome = HoOutcome.Transient; res.Error = "invalid JSON from HO: " + ex.Message; return res; }

            if (status < 200 || status >= 300)
            {
                res.Outcome = HoOutcome.Rejected;
                res.Error = "HTTP " + status + " " + ErrorText(res.Body);
                var retry = res.Body == null ? null : res.Body.SelectToken("error.retryable");
                if (retry != null && retry.Type == JTokenType.Boolean && (bool)retry) res.Outcome = HoOutcome.Transient;
                return res;
            }
            if (res.Body == null) { res.Outcome = HoOutcome.Transient; res.Error = "empty body"; return res; }

            // identity validation: HTTP 200 alone is never trusted
            string sc = (string)res.Body["store_code"], sid = (string)res.Body["store_id"];
            if (!string.Equals(sc, _c.store_code, StringComparison.Ordinal) || !string.Equals(sid, _c.store_id, StringComparison.OrdinalIgnoreCase))
            {
                res.Outcome = HoOutcome.Rejected;
                res.Error = "response store identity mismatch (store_code=" + sc + ")";
                return res;
            }
            var ok = res.Body["ok"];
            if (ok == null || ok.Type != JTokenType.Boolean || !(bool)ok)
            {
                res.Outcome = HoOutcome.Rejected;
                res.Error = "ok=false " + ErrorText(res.Body);
                var retry = res.Body.SelectToken("error.retryable");
                if (retry != null && retry.Type == JTokenType.Boolean && (bool)retry) res.Outcome = HoOutcome.Transient;
                return res;
            }
            res.Outcome = HoOutcome.Ok;
            return res;
        }

        static string ErrorText(JObject b)
        {
            if (b == null) return "";
            var code = b.SelectToken("error.code"); var msg = b.SelectToken("error.message");
            return (code == null ? "" : code.ToString()) + " " + (msg == null ? "" : msg.ToString());
        }

        /// <summary>One-time enrollment: exchanges a one-time code for device credentials (stored with DPAPI).</summary>
        public void Enroll(string enrollmentCode)
        {
            var res = PostUnauthenticated("agent/register", new
            {
                store_code = _c.store_code, store_id = _c.store_id, enrollment_code = enrollmentCode,
                machine_name = Environment.MachineName, agent_version = AgentVersion
            });
            if (res.Outcome != HoOutcome.Ok) throw new InvalidOperationException("enrollment failed: " + res.Error);
            string token = (string)res.Body["device_token"], secret = (string)res.Body["device_secret"], device = (string)res.Body["device_id"];
            if (string.IsNullOrEmpty(token) || string.IsNullOrEmpty(secret) || string.IsNullOrEmpty(device))
                throw new InvalidOperationException("enrollment response incomplete");
            SecretStore.Set("ho_device_token", token);
            SecretStore.Set("ho_device_secret", secret);
            SecretStore.Set("ho_device_id", device);
            Log.Info("AUTH", "device enrolled (device_id=" + device + ")");
        }
    }
}
