using System;
using System.Collections.Generic;
using System.Drawing;
using System.Windows.Forms;

namespace NexoraOrderManagement
{
    // The shell: a top bar (screen switch + store picker + who's signed in), a
    // content area that toggles between the two screens, and the shared product
    // detail panel docked on the right -- the VB Form1 layout.
    internal class MainForm : Form
    {
        private readonly AppConfig _cfg;
        private readonly HoApiClient _api;

        private readonly ComboBox _storeCombo;
        private readonly Label _storeLabel;
        private readonly Button _btnQty;
        private readonly Button _btnSupplier;
        private readonly Panel _host;
        private readonly ProductDetailPanel _detail;
        private readonly QtyCheckView _qty;
        private readonly SupplierOrderingView _supplier;

        private UserControl _active;

        public MainForm(AppConfig cfg, HoApiClient api)
        {
            _cfg = cfg;
            _api = api;

            Text = Ui.AppTitle;
            StartPosition = FormStartPosition.CenterScreen;
            ClientSize = new Size(1180, 720);
            MinimumSize = new Size(920, 560);
            Font = new Font("Segoe UI", 9.5f);

            // --- top bar ---
            var top = new Panel();
            top.Dock = DockStyle.Top;
            top.Height = 48;
            top.BackColor = Color.FromArgb(31, 41, 55);

            _btnQty = NavButton("Qty Check", 8);
            _btnQty.Click += delegate { Show(_qty, _btnQty); };
            _btnSupplier = NavButton("Supplier Ordering", 130);
            _btnSupplier.Click += delegate { Show(_supplier, _btnSupplier); };

            _storeLabel = new Label();
            _storeLabel.ForeColor = Color.White;
            _storeLabel.Font = new Font("Segoe UI", 9.5f, FontStyle.Bold);
            _storeLabel.TextAlign = ContentAlignment.MiddleLeft;
            _storeLabel.SetBounds(320, 0, 220, 48);

            _storeCombo = new ComboBox();
            _storeCombo.DropDownStyle = ComboBoxStyle.DropDownList;
            _storeCombo.SetBounds(320, 12, 200, 24);
            _storeCombo.SelectedIndexChanged += delegate { OnStoreChanged(); };
            _storeCombo.Visible = false;

            var who = new Label();
            who.ForeColor = Color.Gainsboro;
            who.TextAlign = ContentAlignment.MiddleRight;
            who.Dock = DockStyle.Right;
            who.Width = 320;
            who.Padding = new Padding(0, 0, 14, 0);
            var scope = _api.IsFullAccess ? "Admin" : ("Store " + _api.StoreCode);
            who.Text = _api.Username + "  -  " + scope + "   @ " + _api.ActiveBaseUrl;

            top.Controls.Add(_btnQty);
            top.Controls.Add(_btnSupplier);
            top.Controls.Add(_storeLabel);
            top.Controls.Add(_storeCombo);
            top.Controls.Add(who);

            // --- body: content host + detail panel ---
            var split = new SplitContainer();
            split.Dock = DockStyle.Fill;
            split.FixedPanel = FixedPanel.Panel2;
            split.SplitterWidth = 6;

            _host = new Panel();
            _host.Dock = DockStyle.Fill;

            _detail = new ProductDetailPanel(_api);

            _qty = new QtyCheckView(_api);
            _qty.Dock = DockStyle.Fill;
            _qty.Visible = false;
            _qty.ProductSelected += OnProductSelected;

            _supplier = new SupplierOrderingView(_api);
            _supplier.Dock = DockStyle.Fill;
            _supplier.Visible = false;
            _supplier.ProductSelected += OnProductSelected;

            _host.Controls.Add(_qty);
            _host.Controls.Add(_supplier);

            split.Panel1.Controls.Add(_host);
            split.Panel2.Controls.Add(_detail);

            Controls.Add(split);
            Controls.Add(top);

            // SplitterDistance must be set after the control has a width.
            Shown += delegate
            {
                try { split.SplitterDistance = Math.Max(300, split.Width - 440); }
                catch { }
            };

            Load += delegate { Init(); };
        }

        private Button NavButton(string text, int x)
        {
            var b = new Button();
            b.Text = text;
            b.FlatStyle = FlatStyle.Flat;
            b.FlatAppearance.BorderSize = 0;
            b.ForeColor = Color.White;
            b.BackColor = Color.FromArgb(31, 41, 55);
            b.SetBounds(x, 9, 116, 30);
            return b;
        }

        private void Init()
        {
            Ui.Guard(this, delegate
            {
                if (_api.IsFullAccess)
                {
                    _storeCombo.Visible = true;
                    var rows = Json.Rows(_api.GetJson("/api/legacy-order/stores?active_only=true"));
                    _storeCombo.Items.Clear();
                    foreach (var r in rows)
                    {
                        var name = Json.Str(r, "store_name");
                        if (!string.IsNullOrEmpty(name)) _storeCombo.Items.Add(name);
                    }
                    if (_storeCombo.Items.Count > 0) _storeCombo.SelectedIndex = 0;
                }
                else
                {
                    _storeLabel.Visible = true;
                    _storeLabel.Text = "Store: " + _api.StoreCode;
                }
            });

            _detail.SetStore(CurrentStore());
            Show(_qty, _btnQty);
        }

        private string CurrentStore()
        {
            if (_api.IsFullAccess)
                return _storeCombo.SelectedItem == null ? "" : _storeCombo.SelectedItem.ToString();
            return _api.StoreCode;
        }

        private void OnStoreChanged()
        {
            var store = CurrentStore();
            _detail.SetStore(store);
            if (_active != null) LoadActive(store);
        }

        private void OnProductSelected(long productCode, string productName)
        {
            _detail.SetProduct(productCode, productName);
        }

        private void Show(UserControl view, Button nav)
        {
            _qty.Visible = (view == _qty);
            _supplier.Visible = (view == _supplier);
            if (view != null) view.BringToFront();
            _active = view;

            _btnQty.BackColor = (nav == _btnQty) ? Color.FromArgb(59, 130, 246) : Color.FromArgb(31, 41, 55);
            _btnSupplier.BackColor = (nav == _btnSupplier) ? Color.FromArgb(59, 130, 246) : Color.FromArgb(31, 41, 55);

            LoadActive(CurrentStore());
        }

        private void LoadActive(string store)
        {
            if (string.IsNullOrEmpty(store)) return;
            if (_active == _qty) _qty.LoadStore(store);
            else if (_active == _supplier) _supplier.LoadStore(store);
        }
    }
}
