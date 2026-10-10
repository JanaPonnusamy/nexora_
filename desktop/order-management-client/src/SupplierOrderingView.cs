using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Windows.Forms;

namespace NexoraOrderManagement
{
    // Supplier-based ordering, the two VB processes side by side:
    //   * "Auto Pur UpDate"            -> by-supplier mode=history (products this
    //                                     supplier has historically supplied)
    //   * "Order Based on Supplier Stock" -> mode=stock (products matched to the
    //                                     supplier's live SupplierStock)
    // Pick a supplier, see its orderable lines, assign a line to it, and export
    // the order to Excel. The right-hand detail panel follows the selected row.
    internal class SupplierOrderingView : UserControl
    {
        private readonly HoApiClient _api;
        private string _store = "";

        private readonly TextBox _search;
        private readonly ListBox _suppliers;
        private readonly TabControl _tabs;
        private readonly DataGridView _gHistory;
        private readonly DataGridView _gStock;
        private readonly Label _status;

        public event ProductSelectedHandler ProductSelected;

        private class SupplierItem
        {
            public string Code;
            public string Name;
            public override string ToString() { return Name + "  (" + Code + ")"; }
        }

        public SupplierOrderingView(HoApiClient api)
        {
            _api = api;
            Dock = DockStyle.Fill;
            BackColor = Color.White;

            var split = new SplitContainer();
            split.Dock = DockStyle.Fill;
            split.SplitterDistance = 260;
            split.FixedPanel = FixedPanel.Panel1;

            // --- left: supplier search + list ---
            var left = new Panel();
            left.Dock = DockStyle.Fill;

            _search = new TextBox();
            _search.Dock = DockStyle.Top;
            _search.Height = 26;
            var ph = new Label();
            ph.Dock = DockStyle.Top;
            ph.Height = 22;
            ph.Text = "Supplier search (Enter):";
            ph.Padding = new Padding(2, 4, 0, 0);
            _search.KeyDown += delegate(object s, KeyEventArgs e)
            {
                if (e.KeyCode == Keys.Enter) { e.SuppressKeyPress = true; LoadSuppliers(); }
            };

            _suppliers = new ListBox();
            _suppliers.Dock = DockStyle.Fill;
            _suppliers.IntegralHeight = false;
            _suppliers.SelectedIndexChanged += delegate { LoadActiveMode(); };

            left.Controls.Add(_suppliers);
            left.Controls.Add(_search);
            left.Controls.Add(ph);

            // --- right: mode tabs + action bar ---
            var right = new Panel();
            right.Dock = DockStyle.Fill;

            _tabs = new TabControl();
            _tabs.Dock = DockStyle.Fill;
            _gHistory = Ui.NewGrid(true);
            _gStock = Ui.NewGrid(true);
            _gHistory.SelectionChanged += delegate { RaiseSelected(_gHistory); };
            _gStock.SelectionChanged += delegate { RaiseSelected(_gStock); };

            var pHistory = new TabPage("Auto Pur UpDate");
            pHistory.Tag = "history";
            pHistory.Controls.Add(_gHistory);
            var pStock = new TabPage("Order Based on Supplier Stock");
            pStock.Tag = "stock";
            pStock.Controls.Add(_gStock);
            _tabs.TabPages.Add(pHistory);
            _tabs.TabPages.Add(pStock);
            _tabs.SelectedIndexChanged += delegate { LoadActiveMode(); };

            var bar = new FlowLayoutPanel();
            bar.Dock = DockStyle.Bottom;
            bar.Height = 40;
            bar.Padding = new Padding(6, 6, 6, 6);

            var assign = new Button();
            assign.Text = "Assign line to supplier";
            assign.AutoSize = true;
            assign.Click += delegate { AssignCurrent(); };

            var export = new Button();
            export.Text = "Export to Excel";
            export.AutoSize = true;
            export.Click += delegate { ExportCurrent(); };

            _status = new Label();
            _status.AutoSize = true;
            _status.Padding = new Padding(10, 8, 0, 0);

            bar.Controls.Add(assign);
            bar.Controls.Add(export);
            bar.Controls.Add(_status);

            right.Controls.Add(_tabs);
            right.Controls.Add(bar);

            split.Panel1.Controls.Add(left);
            split.Panel2.Controls.Add(right);
            Controls.Add(split);
        }

        public void LoadStore(string store)
        {
            _store = store == null ? "" : store;
            _suppliers.Items.Clear();
            _gHistory.DataSource = null;
            _gStock.DataSource = null;
            _status.Text = "";
            LoadSuppliers();
        }

        private void LoadSuppliers()
        {
            if (string.IsNullOrEmpty(_store)) return;
            Ui.Guard(this, delegate
            {
                var path = "/api/legacy-order/suppliers/" + HoApiClient.Seg(_store) +
                    "?search=" + HoApiClient.Qs(_search.Text);
                var rows = Json.Rows(_api.GetJson(path));
                _suppliers.BeginUpdate();
                _suppliers.Items.Clear();
                foreach (var r in rows)
                {
                    var it = new SupplierItem();
                    it.Code = Json.Str(r, "supplier_code");
                    it.Name = Json.Str(r, "supplier_name");
                    _suppliers.Items.Add(it);
                }
                _suppliers.EndUpdate();
                _status.Text = _suppliers.Items.Count + " supplier(s)";
            });
        }

        private SupplierItem CurrentSupplier()
        {
            return _suppliers.SelectedItem as SupplierItem;
        }

        private string ActiveMode()
        {
            var page = _tabs.SelectedTab;
            return (page != null && page.Tag != null) ? page.Tag.ToString() : "history";
        }

        private DataGridView ActiveGrid()
        {
            return ActiveMode() == "stock" ? _gStock : _gHistory;
        }

        private void LoadActiveMode()
        {
            var sup = CurrentSupplier();
            if (sup == null || string.IsNullOrEmpty(_store)) return;
            var mode = ActiveMode();
            var grid = ActiveGrid();
            Ui.Guard(this, delegate
            {
                var path = "/api/legacy-order/orders/" + HoApiClient.Seg(_store) +
                    "/by-supplier?supplier_code=" + HoApiClient.Qs(sup.Code) + "&mode=" + mode;
                var rows = Json.Rows(_api.GetJson(path));
                grid.DataSource = Ui.ToTable(rows);
                _status.Text = sup.Name + ": " + rows.Count + " orderable line(s) [" + mode + "]";
            });
            RaiseSelected(grid);
        }

        private void AssignCurrent()
        {
            var sup = CurrentSupplier();
            var grid = ActiveGrid();
            if (sup == null) { _status.Text = "Pick a supplier first"; return; }
            if (grid.CurrentRow == null) return;
            var code = Ui.ParseLong(Ui.RowValue(grid, grid.CurrentRow, "ProductCode", "productcode"));
            if (code <= 0) return;
            Ui.Guard(this, delegate
            {
                var body = "{\"supplier_code\": " + JsonString(sup.Code) +
                    ", \"supplier_name\": " + JsonString(sup.Name) + "}";
                var res = Json.Obj(_api.Post(
                    "/api/legacy-order/orders/" + HoApiClient.Seg(_store) + "/" + code + "/assign", body));
                var status = Json.Str(res, "status");
                _status.Text = "Product #" + code + " -> " + sup.Name + " (status " + status + ")";
                LoadActiveMode();   // assigned lines leave the status=0 list
            });
        }

        private void ExportCurrent()
        {
            var sup = CurrentSupplier();
            if (sup == null) { _status.Text = "Pick a supplier first"; return; }
            var mode = ActiveMode();
            using (var dlg = new SaveFileDialog())
            {
                byte[] bytes = null;
                string suggested = "order.xlsx";
                Ui.Guard(this, delegate
                {
                    var body = "{\"supplier_code\": " + JsonString(sup.Code) +
                        ", \"supplier_name\": " + JsonString(sup.Name) +
                        ", \"mode\": " + JsonString(mode) + ", \"split_size\": 0}";
                    bytes = _api.PostForFile(
                        "/api/legacy-order/orders/" + HoApiClient.Seg(_store) + "/export", body, out suggested);
                });
                if (bytes == null) return;   // Guard already reported the error
                dlg.FileName = suggested;
                dlg.Filter = suggested.EndsWith(".zip", StringComparison.OrdinalIgnoreCase)
                    ? "Zip archive (*.zip)|*.zip|All files (*.*)|*.*"
                    : "Excel workbook (*.xlsx)|*.xlsx|All files (*.*)|*.*";
                if (dlg.ShowDialog(this) == DialogResult.OK)
                {
                    try
                    {
                        File.WriteAllBytes(dlg.FileName, bytes);
                        _status.Text = "Exported " + bytes.Length + " bytes -> " + Path.GetFileName(dlg.FileName);
                    }
                    catch (Exception ex)
                    {
                        MessageBox.Show(this, ex.Message, Ui.AppTitle,
                            MessageBoxButtons.OK, MessageBoxIcon.Error);
                    }
                }
            }
        }

        private void RaiseSelected(DataGridView grid)
        {
            if (ProductSelected == null || grid.CurrentRow == null) return;
            var code = Ui.ParseLong(Ui.RowValue(grid, grid.CurrentRow, "ProductCode", "productcode"));
            var name = Ui.RowValue(grid, grid.CurrentRow, "ProductName", "productname");
            if (code > 0) ProductSelected(code, name);
        }

        // JSON-encode a string value (quoted + escaped) without a serializer call.
        private static string JsonString(string s)
        {
            return Json.Write(s == null ? "" : s);
        }
    }
}
