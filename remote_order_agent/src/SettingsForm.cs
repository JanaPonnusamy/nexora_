using System;
using System.Drawing;
using System.Net;
using System.ServiceProcess;
using System.Windows.Forms;

namespace NMVSyncAgent
{
    /// <summary>Settings window (NMVSyncAgent.exe --settings): HO link, HO on/off, connection test, enrollment, service restart.
    /// Edits only %ProgramData%\NMVSyncAgent\agent.json and the DPAPI secret store — never the VB app or SQL.</summary>
    public class SettingsForm : Form
    {
        readonly TextBox _url = new TextBox { Width = 360 };
        readonly CheckBox _enabled = new CheckBox { Text = "Enable HO order/result sync", AutoSize = true };
        readonly CheckBox _insecure = new CheckBox { Text = "Allow plain HTTP (NOT encrypted)", AutoSize = true };
        readonly Label _warn = new Label { AutoSize = true, ForeColor = Color.DarkRed, MaximumSize = new Size(480, 0) };
        readonly Label _status = new Label { AutoSize = true, MaximumSize = new Size(480, 0) };
        readonly TextBox _enroll = new TextBox { Width = 240, UseSystemPasswordChar = true };
        AgentConfig _cfg;

        public SettingsForm()
        {
            Text = "NMV Sync Agent — Settings"; FormBorderStyle = FormBorderStyle.FixedDialog; MaximizeBox = false;
            StartPosition = FormStartPosition.CenterScreen; AutoSize = true; AutoSizeMode = AutoSizeMode.GrowAndShrink; Padding = new Padding(12);
            var p = new TableLayoutPanel { ColumnCount = 2, AutoSize = true, Dock = DockStyle.Fill };
            Func<string, Label> L = s => new Label { Text = s, AutoSize = true, Anchor = AnchorStyles.Left, Margin = new Padding(3, 7, 3, 3) };

            var test = new Button { Text = "Test connection", AutoSize = true };
            var save = new Button { Text = "Save", AutoSize = true };
            var saveRestart = new Button { Text = "Save && restart service", AutoSize = true };
            var enrollBtn = new Button { Text = "Enroll device", AutoSize = true };
            var close = new Button { Text = "Close", AutoSize = true, DialogResult = DialogResult.Cancel };

            p.Controls.Add(L("Store"), 0, 0); p.Controls.Add(new Label { AutoSize = true, Margin = new Padding(3, 7, 3, 3), Name = "store" }, 1, 0);
            p.Controls.Add(L("HO link"), 0, 1); p.Controls.Add(_url, 1, 1);
            p.Controls.Add(new Label(), 0, 2); p.Controls.Add(_enabled, 1, 2);
            p.Controls.Add(new Label(), 0, 3); p.Controls.Add(_insecure, 1, 3);
            p.Controls.Add(new Label(), 0, 4); p.Controls.Add(_warn, 1, 4);
            var row = new FlowLayoutPanel { AutoSize = true }; row.Controls.AddRange(new Control[] { test, save, saveRestart });
            p.Controls.Add(new Label(), 0, 5); p.Controls.Add(row, 1, 5);
            p.Controls.Add(L("Enrollment code"), 0, 6);
            var er = new FlowLayoutPanel { AutoSize = true }; er.Controls.AddRange(new Control[] { _enroll, enrollBtn }); p.Controls.Add(er, 1, 6);
            p.Controls.Add(new Label(), 0, 7); p.Controls.Add(_status, 1, 7);
            p.Controls.Add(new Label(), 0, 8); p.Controls.Add(close, 1, 8);
            Controls.Add(p); CancelButton = close;

            _url.TextChanged += (s, e) => RefreshWarning();
            _insecure.CheckedChanged += (s, e) => RefreshWarning();
            test.Click += (s, e) => TestConnection();
            save.Click += (s, e) => SaveConfig(false);
            saveRestart.Click += (s, e) => SaveConfig(true);
            enrollBtn.Click += (s, e) => EnrollDevice();
            Load += (s, e) => LoadConfig();
        }

        void LoadConfig()
        {
            try
            {
                _cfg = AgentConfig.Load();
                Controls.Find("store", true)[0].Text = _cfg.store_code + "  (" + _cfg.store_id + ")";
                _url.Text = _cfg.ho_base_url; _enabled.Checked = _cfg.ho_enabled; _insecure.Checked = _cfg.allow_insecure_http;
                bool enrolled = SecretStore.Get("ho_device_token") != null;
                Status("Config: " + AgentPaths.ConfigFile + Environment.NewLine + "Device enrolled: " + (enrolled ? "yes" : "no"), false);
            }
            catch (Exception ex) { Status("Cannot load config: " + ex.Message, true); }
        }

        void RefreshWarning()
        {
            Uri u;
            bool http = Uri.TryCreate(_url.Text.Trim(), UriKind.Absolute, out u) && u.Scheme == Uri.UriSchemeHttp;
            _warn.Text = http
                ? (_insecure.Checked ? "WARNING: HO link is plain HTTP. Order data and the device token travel unencrypted. Ask HO to enable HTTPS and switch the link as soon as possible."
                                     : "This link is plain HTTP. Tick 'Allow plain HTTP' to use it (not recommended), or use an https:// link.")
                : "";
        }

        bool ApplyToConfig()
        {
            Uri u;
            string url = _url.Text.Trim().TrimEnd('/');
            if (!Uri.TryCreate(url, UriKind.Absolute, out u) || (u.Scheme != Uri.UriSchemeHttp && u.Scheme != Uri.UriSchemeHttps))
            { Status("HO link must start with http:// or https://", true); return false; }
            if (u.Scheme == Uri.UriSchemeHttp && !_insecure.Checked) { Status("Plain HTTP link: tick 'Allow plain HTTP' or use https://", true); return false; }
            _cfg.ho_base_url = url; _cfg.ho_enabled = _enabled.Checked; _cfg.allow_insecure_http = _insecure.Checked && u.Scheme == Uri.UriSchemeHttp;
            return true;
        }

        void SaveConfig(bool restart)
        {
            if (_cfg == null || !ApplyToConfig()) return;
            try
            {
                _cfg.Save();
                Log.Info("CONFIG", "settings saved via Settings window: ho_base_url=" + _cfg.ho_base_url + " ho_enabled=" + _cfg.ho_enabled + " insecure_http=" + _cfg.allow_insecure_http);
                if (!restart) { Status("Saved. The service picks up changes on restart.", false); return; }
                using (var sc = new ServiceController("NMVSyncAgent"))
                {
                    if (sc.Status != ServiceControllerStatus.Stopped) { sc.Stop(); sc.WaitForStatus(ServiceControllerStatus.Stopped, TimeSpan.FromSeconds(40)); }
                    sc.Start(); sc.WaitForStatus(ServiceControllerStatus.Running, TimeSpan.FromSeconds(40));
                }
                Status("Saved and service restarted.", false);
            }
            catch (UnauthorizedAccessException) { Status("Access denied. Run Settings as Administrator.", true); }
            catch (InvalidOperationException ex) { Status("Saved config, but service control failed: " + ex.Message, true); }
            catch (Exception ex) { Status("Save failed: " + ex.Message, true); }
        }

        void TestConnection()
        {
            Uri u;
            if (!Uri.TryCreate(_url.Text.Trim(), UriKind.Absolute, out u)) { Status("Invalid link", true); return; }
            Cursor = Cursors.WaitCursor;
            try
            {
                ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;
                var req = (HttpWebRequest)WebRequest.Create(u);
                req.Method = "GET"; req.Timeout = 10000; req.AllowAutoRedirect = false;
                int code;
                try { using (var r = (HttpWebResponse)req.GetResponse()) code = (int)r.StatusCode; }
                catch (WebException wex)
                {
                    var r = wex.Response as HttpWebResponse;
                    if (r == null) { Status("NOT reachable: " + wex.Status + " — " + wex.Message, true); return; }
                    code = (int)r.StatusCode; r.Close();
                }
                Status("Reachable: HO answered HTTP " + code + " (" + u.Scheme.ToUpperInvariant() + ").", false);
            }
            catch (Exception ex) { Status("Test failed: " + ex.Message, true); }
            finally { Cursor = Cursors.Default; }
        }

        void EnrollDevice()
        {
            if (_cfg == null || !ApplyToConfig()) return;
            if (string.IsNullOrWhiteSpace(_enroll.Text)) { Status("Enter the one-time enrollment code issued by HO.", true); return; }
            if (!_cfg.ho_enabled) { Status("Tick 'Enable HO order/result sync' first.", true); return; }
            try
            {
                _cfg.Save();
                new HoClient(_cfg).Enroll(_enroll.Text.Trim());
                _enroll.Clear();
                Status("Device enrolled. Use 'Save & restart service' to start syncing.", false);
            }
            catch (Exception ex) { Status("Enrollment failed: " + ex.Message, true); }
        }

        void Status(string s, bool error) { _status.Text = s; _status.ForeColor = error ? Color.DarkRed : Color.DarkGreen; }
    }
}
