using System;
using System.Collections.Generic;
using System.IO;

namespace NexoraOrderManagement
{
    // Persisted to %APPDATA%\NexoraOrderManagement\config.json. Holds the ordered
    // list of HO URLs to try (public endpoint first, LAN fallback), whether to
    // accept the HO's TLS cert without a trust chain, and the last username.
    internal class AppConfig
    {
        public List<string> HoUrls { get; set; }
        public bool AllowInsecureTls { get; set; }
        public string LastUsername { get; set; }

        public AppConfig()
        {
            HoUrls = new List<string>();
            AllowInsecureTls = true;
            LastUsername = "";
        }

        public static string Dir()
        {
            var baseDir = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
            return Path.Combine(baseDir, "NexoraOrderManagement");
        }

        public static string FilePath()
        {
            return Path.Combine(Dir(), "config.json");
        }

        public static AppConfig Load()
        {
            var cfg = new AppConfig();
            try
            {
                var path = FilePath();
                if (File.Exists(path))
                {
                    var d = Json.Obj(Json.Parse(File.ReadAllText(path)));
                    object urls;
                    if (d.TryGetValue("ho_urls", out urls))
                    {
                        var arr = urls as object[];
                        if (arr != null)
                        {
                            foreach (var u in arr)
                            {
                                var s = Convert.ToString(u);
                                if (!string.IsNullOrEmpty(s)) cfg.HoUrls.Add(s.Trim());
                            }
                        }
                    }
                    object ins;
                    if (d.TryGetValue("allow_insecure_tls", out ins) && ins != null)
                        cfg.AllowInsecureTls = Convert.ToBoolean(ins);
                    object lu;
                    if (d.TryGetValue("last_username", out lu) && lu != null)
                        cfg.LastUsername = Convert.ToString(lu);
                }
            }
            catch { }

            if (cfg.HoUrls.Count == 0)
            {
                // Public NAT entry first, LAN build node as a fallback.
                cfg.HoUrls.Add("https://122.252.246.181:8443");
                cfg.HoUrls.Add("http://192.168.10.80:8000");
            }
            return cfg;
        }

        public void Save()
        {
            try
            {
                Directory.CreateDirectory(Dir());
                var d = new Dictionary<string, object>();
                d["ho_urls"] = HoUrls;
                d["allow_insecure_tls"] = AllowInsecureTls;
                d["last_username"] = LastUsername;
                File.WriteAllText(FilePath(), Json.Write(d));
            }
            catch { }
        }

        // Move the given URL to the front of the try-order (so the one the user
        // picked at login is attempted first next time), de-duplicating.
        public void PreferUrl(string url)
        {
            if (string.IsNullOrEmpty(url)) return;
            url = url.Trim().TrimEnd('/');
            var next = new List<string>();
            next.Add(url);
            foreach (var u in HoUrls)
            {
                var t = (u == null ? "" : u.Trim().TrimEnd('/'));
                if (t.Length > 0 && !string.Equals(t, url, StringComparison.OrdinalIgnoreCase))
                    next.Add(t);
            }
            HoUrls = next;
        }
    }
}
