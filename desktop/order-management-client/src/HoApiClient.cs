using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;

namespace NexoraOrderManagement
{
    internal class ApiException : Exception
    {
        public int StatusCode { get; private set; }
        public ApiException(int status, string message) : base(message) { StatusCode = status; }
    }

    // Talks to the HO backend's /api/legacy-order/* API (never the DB). All data
    // comes through this client; it logs in once (trying each configured HO URL
    // until one answers), then pins to that node for the session. Calls are made
    // synchronously (HttpClient awaits with ConfigureAwait(false) internally, so
    // blocking on the UI thread does not deadlock).
    internal class HoApiClient
    {
        private readonly AppConfig _cfg;
        private readonly HttpClient _http;

        public string Token { get; private set; }
        public string ActiveBaseUrl { get; private set; }
        public Dictionary<string, object> Claims { get; private set; }

        public HoApiClient(AppConfig cfg)
        {
            _cfg = cfg;
            Claims = new Dictionary<string, object>();

            // Older .NET Framework defaults omit TLS 1.2 -- required for most
            // modern HTTPS endpoints. Enable it process-wide.
            ServicePointManager.SecurityProtocol =
                SecurityProtocolType.Tls12 | SecurityProtocolType.Tls11 | SecurityProtocolType.Tls;
            if (_cfg.AllowInsecureTls)
                ServicePointManager.ServerCertificateValidationCallback =
                    delegate { return true; };

            _http = new HttpClient(new HttpClientHandler());
            _http.Timeout = TimeSpan.FromSeconds(90);
        }

        public bool IsFullAccess
        {
            get
            {
                object pu;
                if (Claims.TryGetValue("is_platform_user", out pu) && pu != null && Convert.ToBoolean(pu))
                    return true;
                object rn;
                if (Claims.TryGetValue("role_names", out rn))
                {
                    var arr = rn as object[];
                    if (arr != null)
                        foreach (var r in arr)
                        {
                            var s = Convert.ToString(r).ToUpperInvariant();
                            if (s == "SUPER_ADMIN" || s == "PLATFORM_OWNER") return true;
                        }
                }
                return false;
            }
        }

        public string StoreCode
        {
            get
            {
                object sc;
                if (Claims.TryGetValue("store_code", out sc) && sc != null)
                    return Convert.ToString(sc);
                return "";
            }
        }

        public string Username
        {
            get
            {
                object u;
                if (Claims.TryGetValue("username", out u) && u != null)
                    return Convert.ToString(u);
                return "";
            }
        }

        public void Login(string username, string password)
        {
            Exception last = null;
            var body = new Dictionary<string, object>();
            body["username"] = username;
            body["password"] = password;
            var payload = Json.Write(body);

            foreach (var baseUrl in _cfg.HoUrls)
            {
                var cleanBase = (baseUrl == null ? "" : baseUrl.Trim().TrimEnd('/'));
                if (cleanBase.Length == 0) continue;
                try
                {
                    var req = new HttpRequestMessage(HttpMethod.Post, cleanBase + "/api/auth/login");
                    req.Content = new StringContent(payload, Encoding.UTF8, "application/json");
                    var resp = _http.SendAsync(req).GetAwaiter().GetResult();
                    var text = resp.Content.ReadAsStringAsync().GetAwaiter().GetResult();
                    if (!resp.IsSuccessStatusCode)
                    {
                        // A real auth rejection (bad credentials, session clash)
                        // is the same on every node -- surface it, do not fall
                        // through to the next URL as if this one were unreachable.
                        throw new ApiException((int)resp.StatusCode, ExtractDetail(text, resp.ReasonPhrase));
                    }
                    var d = Json.Obj(Json.Parse(text));
                    Token = Json.Str(d, "token");
                    if (string.IsNullOrEmpty(Token))
                        throw new ApiException(500, "Login response contained no token.");
                    Claims = JwtHelper.DecodePayload(Token);
                    ActiveBaseUrl = cleanBase;
                    return;
                }
                catch (ApiException) { throw; }
                catch (Exception ex) { last = ex; }
            }
            throw new Exception("Could not reach HO at any configured address." +
                (last != null ? " Last error: " + last.Message : ""));
        }

        private HttpRequestMessage Build(HttpMethod method, string path, string jsonBody)
        {
            var req = new HttpRequestMessage(method, ActiveBaseUrl + path);
            req.Headers.Authorization = new AuthenticationHeaderValue("Bearer", Token);
            if (jsonBody != null)
                req.Content = new StringContent(jsonBody, Encoding.UTF8, "application/json");
            return req;
        }

        private string Send(HttpMethod method, string path, string jsonBody)
        {
            var resp = _http.SendAsync(Build(method, path, jsonBody)).GetAwaiter().GetResult();
            var text = resp.Content.ReadAsStringAsync().GetAwaiter().GetResult();
            if (!resp.IsSuccessStatusCode)
                throw new ApiException((int)resp.StatusCode, ExtractDetail(text, resp.ReasonPhrase));
            return text;
        }

        public object GetJson(string path) { return Json.Parse(Send(HttpMethod.Get, path, null)); }
        public object Patch(string path, string jsonBody) { return Json.Parse(Send(new HttpMethod("PATCH"), path, jsonBody)); }
        public object Post(string path, string jsonBody) { return Json.Parse(Send(HttpMethod.Post, path, jsonBody)); }

        // Export returns a binary file (xlsx/zip); read raw bytes + the filename
        // from Content-Disposition.
        public byte[] PostForFile(string path, string jsonBody, out string fileName)
        {
            var resp = _http.SendAsync(Build(HttpMethod.Post, path, jsonBody)).GetAwaiter().GetResult();
            if (!resp.IsSuccessStatusCode)
            {
                var text = resp.Content.ReadAsStringAsync().GetAwaiter().GetResult();
                throw new ApiException((int)resp.StatusCode, ExtractDetail(text, resp.ReasonPhrase));
            }
            fileName = "order.xlsx";
            if (resp.Content.Headers.ContentDisposition != null &&
                !string.IsNullOrEmpty(resp.Content.Headers.ContentDisposition.FileName))
                fileName = resp.Content.Headers.ContentDisposition.FileName.Trim('"');
            return resp.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult();
        }

        private static string ExtractDetail(string body, string fallback)
        {
            try
            {
                var d = Json.Obj(Json.Parse(body));
                var detail = Json.Str(d, "detail");
                if (!string.IsNullOrEmpty(detail)) return detail;
            }
            catch { }
            return string.IsNullOrEmpty(fallback) ? "Request failed" : fallback;
        }

        // ---- URL helpers --------------------------------------------------
        public static string Seg(string value)
        {
            return Uri.EscapeDataString(value == null ? "" : value);
        }

        public static string Qs(string value)
        {
            return Uri.EscapeDataString(value == null ? "" : value);
        }
    }
}
