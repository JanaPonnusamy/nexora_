using System;
using System.Drawing;
using System.Windows.Forms;

namespace NexoraOrderManagement
{
    // First screen: HO address + credentials. On success it builds the
    // authenticated HoApiClient and exposes it to the caller. The HO URL and the
    // "accept certificate" choice are persisted so next launch is one click.
    internal class LoginForm : Form
    {
        private readonly AppConfig _cfg;
        private readonly TextBox _url;
        private readonly TextBox _user;
        private readonly TextBox _pass;
        private readonly CheckBox _insecure;
        private readonly Button _login;
        private readonly Label _msg;

        public HoApiClient Api { get; private set; }

        public LoginForm(AppConfig cfg)
        {
            _cfg = cfg;
            Text = Ui.AppTitle + " - Sign in";
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;
            MinimizeBox = false;
            StartPosition = FormStartPosition.CenterScreen;
            ClientSize = new Size(420, 250);
            Font = new Font("Segoe UI", 9.5f);

            var title = new Label();
            title.Text = "Nexora Order Management";
            title.Font = new Font("Segoe UI", 13f, FontStyle.Bold);
            title.SetBounds(16, 14, 388, 28);

            _url = Field("HO address", 54);
            _url.Text = _cfg.HoUrls.Count > 0 ? _cfg.HoUrls[0] : "";

            _user = Field("Username", 98);
            _user.Text = _cfg.LastUsername;

            _pass = Field("Password", 142);
            _pass.UseSystemPasswordChar = true;
            _pass.KeyDown += delegate(object s, KeyEventArgs e)
            {
                if (e.KeyCode == Keys.Enter) { e.SuppressKeyPress = true; DoLogin(); }
            };

            _insecure = new CheckBox();
            _insecure.Text = "Accept the HO server's certificate (self-signed)";
            _insecure.Checked = _cfg.AllowInsecureTls;
            _insecure.SetBounds(120, 176, 290, 22);

            _login = new Button();
            _login.Text = "Sign in";
            _login.SetBounds(120, 204, 100, 30);
            _login.Click += delegate { DoLogin(); };
            AcceptButton = _login;

            _msg = new Label();
            _msg.ForeColor = Color.Firebrick;
            _msg.SetBounds(230, 208, 180, 40);
            _msg.TextAlign = ContentAlignment.MiddleLeft;

            Controls.Add(title);
            Controls.Add(_insecure);
            Controls.Add(_login);
            Controls.Add(_msg);
        }

        // Adds a left label + a textbox at the given Y; returns the textbox.
        private TextBox Field(string label, int y)
        {
            var lbl = new Label();
            lbl.Text = label;
            lbl.SetBounds(16, y + 3, 100, 20);
            var tb = new TextBox();
            tb.SetBounds(120, y, 284, 24);
            Controls.Add(lbl);
            Controls.Add(tb);
            return tb;
        }

        private void DoLogin()
        {
            _msg.Text = "";
            var url = _url.Text.Trim();
            if (url.Length == 0) { _msg.Text = "Enter the HO address"; return; }
            _login.Enabled = false;
            Cursor = Cursors.WaitCursor;
            try
            {
                _cfg.AllowInsecureTls = _insecure.Checked;
                _cfg.PreferUrl(url);
                _cfg.LastUsername = _user.Text.Trim();
                var api = new HoApiClient(_cfg);
                api.Login(_user.Text.Trim(), _pass.Text);
                Api = api;
                _cfg.Save();
                DialogResult = DialogResult.OK;
                Close();
            }
            catch (ApiException ex)
            {
                _msg.Text = ex.Message;
            }
            catch (Exception ex)
            {
                _msg.Text = ex.Message;
            }
            finally
            {
                _login.Enabled = true;
                Cursor = Cursors.Default;
            }
        }
    }
}
