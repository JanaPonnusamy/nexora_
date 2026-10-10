using System;
using System.Collections.Generic;
using System.Data;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Windows.Forms;
using System.Windows.Forms.DataVisualization.Charting;

namespace NexoraOrderManagement
{
    // Faithful replica of the VB.NET OrderManagement Form1: same single-window
    // absolute layout, same controls at the same positions, the same blue
    // background, and the same monthly Purchase/Sales/Stock column chart. Data
    // comes from the HO /api/legacy-order/* API (no direct DB), reusing
    // HoApiClient. Positions/sizes are copied verbatim from Form1.Designer.vb.
    internal class OrderForm : Form
    {
        private readonly HoApiClient _api;
        private readonly AppConfig _cfg;

        // --- controls (same names as the VB form) ---
        private Label lblExportStatus, lblSelectProcess, lblProductType, lblSupplierName, lblSplitCount, lblstatus;
        private TextBox txtStoreSearch, txtSupplierSearch, txtExportPath, txtSplitCount;
        private ComboBox cboProcess, cboProductType;
        private DataGridView dgvMain, dgvStoreList, dgvSupplierList, dgvOrderDetails,
                             dgvSalesDetails, dgvPurchaseDetails, DgvMainFooter;
        private Chart Chart1;
        private Button btnExport, btnExportJson, btnCompareSelectedSupplier, Syncbtn, btnExit,
                       btnBrowseExportPath, btnSplitExcel, btnImportStock, btnMapping, Button1;
        private GroupBox GroupBox_MinMaxSetting;
        private RadioButton LocalDB, RemoteDB;
        private ProgressBar ProgressBar1;

        private string _store = "";
        private string _supplierCode = "";
        private string _supplierName = "";

        private static readonly Font GridFont = new Font("Microsoft Sans Serif", 8.25f);
        private static readonly Font LblFont = new Font("Segoe UI", 10f, FontStyle.Bold);

        private const string PROC_QTY = "Pending Order Qty Check";
        private const string PROC_HIST = "Auto Pur UpDate";
        private const string PROC_STOCK = "Order Based on Supplier Stock";

        public OrderForm(AppConfig cfg, HoApiClient api)
        {
            _cfg = cfg;
            _api = api;
            BuildUi();
            Load += delegate { InitData(); };
        }

        // ------------------------------------------------------------------
        // UI construction -- coordinates are verbatim from Form1.Designer.vb
        // ------------------------------------------------------------------
        private void BuildUi()
        {
            Text = "Order Management";
            ClientSize = new Size(1367, 766);
            WindowState = FormWindowState.Maximized;
            StartPosition = FormStartPosition.CenterScreen;
            Font = new Font("Segoe UI", 9f);
            var bg = LoadBackground();
            if (bg != null) { BackgroundImage = bg; BackgroundImageLayout = ImageLayout.Stretch; }

            lblExportStatus = Lbl("Select Store", 8, 12);
            txtStoreSearch = Txt(102, 13, 107, 20);
            lblSelectProcess = Lbl("Select Process", 214, 13);
            cboProcess = Combo(323, 13, 151);
            lblProductType = Lbl("Product Type", 479, 15);
            cboProductType = Combo(578, 12, 151);
            lblSupplierName = Lbl("Supplier Name", 739, 12); lblSupplierName.Visible = false;
            txtSupplierSearch = Txt(886, 10, 295, 20); txtSupplierSearch.Visible = false;

            dgvMain = Grid(4, 36, 878, 510, false);
            DgvMainFooter = Grid(4, 546, 878, 27, true); DgvMainFooter.ColumnHeadersVisible = false;
            dgvOrderDetails = Grid(5, 573, 878, 122, true);
            dgvStoreList = Grid(102, 36, 245, 151, true);
            dgvSupplierList = Grid(838, 36, 518, 140, true); dgvSupplierList.Visible = false;
            dgvPurchaseDetails = Grid(886, 36, 468, 200, true);
            dgvSalesDetails = Grid(886, 240, 468, 200, true);

            Chart1 = new Chart();
            Chart1.Location = new Point(886, 440);
            Chart1.Size = new Size(468, 244);
            Chart1.BackColor = Color.White;

            btnExport = Btn("Export", 886, 689, 75, 24);
            btnExportJson = Btn("Web Export", 949, 689, 75, 24);
            btnCompareSelectedSupplier = Btn("Compare", 1019, 689, 67, 24);
            Syncbtn = Btn("Sync", 1080, 689, 55, 23);
            btnExit = Btn("Exit", 1132, 689, 53, 24);
            txtExportPath = Txt(886, 717, 220, 20);
            btnBrowseExportPath = Btn("...", 1110, 715, 30, 24);
            lblSplitCount = Lbl("Qty/File:", 886, 744); lblSplitCount.Font = Font;
            txtSplitCount = Txt(966, 741, 50, 20);
            btnSplitExcel = Btn("Split Excel File", 1030, 740, 110, 24);
            btnImportStock = Btn("Import Stock", 1150, 740, 90, 24);
            btnMapping = Btn("Mapping", 1281, 8, 75, 22);
            Button1 = Btn("Pull", 1212, 8, 75, 22);

            GroupBox_MinMaxSetting = new GroupBox();
            GroupBox_MinMaxSetting.Text = "Query Source";
            GroupBox_MinMaxSetting.Location = new Point(1185, 681);
            GroupBox_MinMaxSetting.Size = new Size(169, 37);
            GroupBox_MinMaxSetting.BackColor = Color.Transparent;
            RemoteDB = new RadioButton(); RemoteDB.Text = "Remote DB"; RemoteDB.Location = new Point(5, 15); RemoteDB.AutoSize = true;
            LocalDB = new RadioButton(); LocalDB.Text = "Local DB"; LocalDB.Location = new Point(91, 15); LocalDB.AutoSize = true; LocalDB.Checked = true;
            GroupBox_MinMaxSetting.Controls.Add(RemoteDB);
            GroupBox_MinMaxSetting.Controls.Add(LocalDB);

            ProgressBar1 = new ProgressBar(); ProgressBar1.Location = new Point(12, 695); ProgressBar1.Size = new Size(869, 13); ProgressBar1.Visible = false;
            lblstatus = Lbl("", 12, 671);

            // Add back-to-front: main grids first, overlays (store/supplier list) on top.
            Controls.Add(dgvMain);
            Controls.Add(DgvMainFooter);
            Controls.Add(dgvOrderDetails);
            Controls.Add(dgvPurchaseDetails);
            Controls.Add(dgvSalesDetails);
            Controls.Add(Chart1);
            Controls.Add(dgvSupplierList);
            Controls.Add(dgvStoreList);
            foreach (Control c in new Control[] {
                lblExportStatus, txtStoreSearch, lblSelectProcess, cboProcess, lblProductType,
                cboProductType, lblSupplierName, txtSupplierSearch, btnExport, btnExportJson,
                btnCompareSelectedSupplier, Syncbtn, btnExit, txtExportPath, btnBrowseExportPath,
                lblSplitCount, txtSplitCount, btnSplitExcel, btnImportStock, btnMapping, Button1,
                GroupBox_MinMaxSetting, ProgressBar1, lblstatus })
                Controls.Add(c);

            WireEvents();
        }

        private void WireEvents()
        {
            txtStoreSearch.KeyDown += delegate(object s, KeyEventArgs e) { if (e.KeyCode == Keys.Enter) { e.SuppressKeyPress = true; LoadStores(); ShowStoreList(true); } };
            txtStoreSearch.Enter += delegate { ShowStoreList(true); };
            dgvStoreList.CellClick += delegate(object s, DataGridViewCellEventArgs e) { if (e.RowIndex >= 0) PickStore(e.RowIndex); };
            dgvStoreList.KeyDown += delegate(object s, KeyEventArgs e) { if (e.KeyCode == Keys.Enter && dgvStoreList.CurrentRow != null) PickStore(dgvStoreList.CurrentRow.Index); };

            cboProcess.SelectedIndexChanged += delegate { LoadProcess(); };
            cboProductType.SelectedIndexChanged += delegate { if (cboProcess.Text == PROC_QTY) LoadQtyCheck(); };

            txtSupplierSearch.KeyDown += delegate(object s, KeyEventArgs e) { if (e.KeyCode == Keys.Enter) { e.SuppressKeyPress = true; LoadSuppliers(); ShowSupplierList(true); } };
            txtSupplierSearch.Enter += delegate { ShowSupplierList(true); };
            dgvSupplierList.CellClick += delegate(object s, DataGridViewCellEventArgs e) { if (e.RowIndex >= 0) PickSupplier(e.RowIndex); };
            dgvSupplierList.KeyDown += delegate(object s, KeyEventArgs e) { if (e.KeyCode == Keys.Enter && dgvSupplierList.CurrentRow != null) PickSupplier(dgvSupplierList.CurrentRow.Index); };

            dgvMain.SelectionChanged += delegate { LoadDetailsForCurrent(); };
            dgvMain.CellEndEdit += DgvMain_CellEndEdit;

            LocalDB.CheckedChanged += delegate { LoadDetailsForCurrent(); };
            RemoteDB.CheckedChanged += delegate { LoadDetailsForCurrent(); };

            btnExit.Click += delegate { Close(); };
            btnExport.Click += delegate { ExportOrder(); };
            btnCompareSelectedSupplier.Click += delegate { CompareSupplier(); };

            EventHandler ho = delegate { MessageBox.Show(this, "This action runs in the Head Office console, not in this client.", Ui.AppTitle, MessageBoxButtons.OK, MessageBoxIcon.Information); };
            Syncbtn.Click += ho; Button1.Click += ho; btnMapping.Click += ho;
            btnImportStock.Click += ho; btnExportJson.Click += ho; btnSplitExcel.Click += ho; btnBrowseExportPath.Click += ho;
        }

        // ------------------------------------------------------------------
        // data
        // ------------------------------------------------------------------
        private void InitData()
        {
            cboProcess.Items.Clear();
            cboProcess.Items.AddRange(new object[] { PROC_QTY, PROC_HIST, PROC_STOCK });
            cboProductType.Items.Clear();
            cboProductType.Items.AddRange(new object[] { "All", "Pharma", "Non Pharma" });
            cboProductType.SelectedIndex = 0;

            LoadStores();
            // store user has exactly one store -> auto-pick it
            if (!_api.IsFullAccess && dgvStoreList.Rows.Count >= 1)
                PickStore(0);
            else
                ShowStoreList(true);
        }

        private void LoadStores()
        {
            Ui.Guard(this, delegate
            {
                List<Dictionary<string, object>> rows;
                if (_api.IsFullAccess)
                {
                    rows = Json.Rows(_api.GetJson("/api/legacy-order/stores?active_only=true"));
                }
                else
                {
                    rows = new List<Dictionary<string, object>>();
                    var d = new Dictionary<string, object>();
                    d["store_name"] = _api.StoreCode;
                    rows.Add(d);
                }
                var filter = txtStoreSearch.Text.Trim();
                var table = new DataTable();
                table.Columns.Add("StoreName", typeof(string));
                foreach (var r in rows)
                {
                    var name = Json.Str(r, "store_name");
                    if (filter.Length == 0 || name.IndexOf(filter, StringComparison.OrdinalIgnoreCase) >= 0)
                        table.Rows.Add(name);
                }
                dgvStoreList.DataSource = table;
            });
        }

        private void PickStore(int rowIndex)
        {
            if (rowIndex < 0 || rowIndex >= dgvStoreList.Rows.Count) return;
            _store = Ui.RowValue(dgvStoreList, dgvStoreList.Rows[rowIndex], "StoreName");
            lblExportStatus.Text = "Store: " + _store;
            txtStoreSearch.Text = _store;
            ShowStoreList(false);
            if (cboProcess.SelectedIndex < 0) cboProcess.SelectedIndex = 0;
            else LoadProcess();
        }

        private void LoadProcess()
        {
            if (string.IsNullOrEmpty(_store)) return;
            ClearDetails();
            dgvMain.DataSource = null;
            var proc = cboProcess.Text;
            bool supplierMode = (proc == PROC_HIST || proc == PROC_STOCK);
            lblSupplierName.Visible = supplierMode;
            txtSupplierSearch.Visible = supplierMode;
            btnExport.Enabled = supplierMode;
            if (supplierMode)
            {
                _supplierCode = ""; _supplierName = "";
                LoadSuppliers();
                ShowSupplierList(true);
                lblstatus.Text = "Pick a supplier for \"" + proc + "\"";
            }
            else
            {
                ShowSupplierList(false);
                LoadQtyCheck();
            }
        }

        private void LoadQtyCheck()
        {
            Ui.Guard(this, delegate
            {
                var rows = Json.Rows(_api.GetJson("/api/legacy-order/qty-check/" + HoApiClient.Seg(_store)));
                var type = cboProductType.Text;
                if (type != "All" && type.Length > 0)
                {
                    var f = new List<Dictionary<string, object>>();
                    foreach (var r in rows)
                        if (string.Equals(Json.Str(r, "producttypename"), type, StringComparison.OrdinalIgnoreCase))
                            f.Add(r);
                    rows = f;
                }
                dgvMain.DataSource = Ui.ToTable(rows);
                MakeOrderQtyEditable();
                lblstatus.Text = _store + " - Qty Check: " + rows.Count + " pending line(s)";
            });
            LoadDetailsForCurrent();
        }

        private void LoadSuppliers()
        {
            Ui.Guard(this, delegate
            {
                var rows = Json.Rows(_api.GetJson("/api/legacy-order/suppliers/" + HoApiClient.Seg(_store) +
                    "?search=" + HoApiClient.Qs(txtSupplierSearch.Text)));
                var table = new DataTable();
                table.Columns.Add("SupplierCode", typeof(string));
                table.Columns.Add("SupplierName", typeof(string));
                foreach (var r in rows) table.Rows.Add(Json.Str(r, "supplier_code"), Json.Str(r, "supplier_name"));
                dgvSupplierList.DataSource = table;
                lblstatus.Text = rows.Count + " supplier(s)";
            });
        }

        private void PickSupplier(int rowIndex)
        {
            if (rowIndex < 0 || rowIndex >= dgvSupplierList.Rows.Count) return;
            _supplierCode = Ui.RowValue(dgvSupplierList, dgvSupplierList.Rows[rowIndex], "SupplierCode");
            _supplierName = Ui.RowValue(dgvSupplierList, dgvSupplierList.Rows[rowIndex], "SupplierName");
            lblSupplierName.Text = _supplierName;
            txtSupplierSearch.Text = _supplierName;
            ShowSupplierList(false);
            var mode = (cboProcess.Text == PROC_STOCK) ? "stock" : "history";
            Ui.Guard(this, delegate
            {
                var rows = Json.Rows(_api.GetJson("/api/legacy-order/orders/" + HoApiClient.Seg(_store) +
                    "/by-supplier?supplier_code=" + HoApiClient.Qs(_supplierCode) + "&mode=" + mode));
                dgvMain.DataSource = Ui.ToTable(rows);
                lblstatus.Text = _supplierName + " [" + mode + "]: " + rows.Count + " orderable line(s)";
            });
            LoadDetailsForCurrent();
        }

        private void LoadDetailsForCurrent()
        {
            if (dgvMain.CurrentRow == null || string.IsNullOrEmpty(_store)) return;
            var code = Ui.ParseLong(Ui.RowValue(dgvMain, dgvMain.CurrentRow, "ProductCode", "productcode"));
            if (code <= 0) return;
            var mode = RemoteDB.Checked ? "remote" : "local";
            Ui.Guard(this, delegate
            {
                var baseP = "/api/legacy-order/qty-check/" + HoApiClient.Seg(_store) + "/" + code;
                dgvPurchaseDetails.DataSource = Ui.ToTable(Json.Rows(_api.GetJson(baseP + "/purchase-details?mode=" + mode)));
                dgvSalesDetails.DataSource = Ui.ToTable(Json.Rows(_api.GetJson(baseP + "/sales-details?mode=" + mode)));
                BuildChart(Json.Rows(_api.GetJson(baseP + "/monthly-stats?mode=" + mode)),
                    Ui.RowValue(dgvMain, dgvMain.CurrentRow, "ProductName", "productname"));
            });
        }

        // monthly Purchase/Sales/Stock column chart -- same series + colors as VB
        private void BuildChart(List<Dictionary<string, object>> rows, string productName)
        {
            Chart1.Series.Clear();
            Chart1.ChartAreas.Clear();
            Chart1.Legends.Clear();
            Chart1.Titles.Clear();
            var ca = new ChartArea("ca");
            Chart1.ChartAreas.Add(ca);
            Chart1.Titles.Add("Monthly Statistics - " + productName);

            AddSeries(rows, "Purchase", "purchase", Color.Blue);
            AddSeries(rows, "Sales", "sales", Color.Green);
            AddSeries(rows, "Stock", "stock", Color.Red);

            var legend = new Legend("legend");
            legend.Docking = Docking.Bottom;
            Chart1.Legends.Add(legend);
        }

        private void AddSeries(List<Dictionary<string, object>> rows, string name, string key, Color color)
        {
            var s = new Series(name);
            s.ChartType = SeriesChartType.Column;
            s.Color = color;
            s.IsValueShownAsLabel = false;
            foreach (var r in rows)
                s.Points.AddXY(Json.Str(r, "month"), ParseNum(r, key));
            Chart1.Series.Add(s);
        }

        private void DgvMain_CellEndEdit(object sender, DataGridViewCellEventArgs e)
        {
            if (cboProcess.Text != PROC_QTY) return;
            if (e.RowIndex < 0 || e.ColumnIndex < 0) return;
            if (!string.Equals(dgvMain.Columns[e.ColumnIndex].Name, "orderqty", StringComparison.OrdinalIgnoreCase)) return;
            var row = dgvMain.Rows[e.RowIndex];
            var code = Ui.ParseLong(Ui.RowValue(dgvMain, row, "productcode", "ProductCode"));
            var qty = Ui.ParseInt(Convert.ToString(row.Cells[e.ColumnIndex].Value));
            if (code <= 0) return;
            Ui.Guard(this, delegate
            {
                var res = Json.Obj(_api.Patch("/api/legacy-order/qty-check/" + HoApiClient.Seg(_store) + "/" + code,
                    "{\"order_qty\": " + qty + "}"));
                lblstatus.Text = "Reviewed #" + code + " -> " + qty + " (" + Json.Str(res, "remarks") + ")";
                var table = dgvMain.DataSource as DataTable;
                if (table != null && e.RowIndex < table.Rows.Count) { table.Rows[e.RowIndex].Delete(); table.AcceptChanges(); }
            });
        }

        private void ExportOrder()
        {
            if (string.IsNullOrEmpty(_supplierCode)) { lblstatus.Text = "Pick a supplier first"; return; }
            var mode = (cboProcess.Text == PROC_STOCK) ? "stock" : "history";
            byte[] bytes = null; string suggested = "order.xlsx";
            Ui.Guard(this, delegate
            {
                var body = "{\"supplier_code\": " + Json.Write(_supplierCode) +
                    ", \"supplier_name\": " + Json.Write(_supplierName) +
                    ", \"mode\": " + Json.Write(mode) + ", \"split_size\": 0}";
                bytes = _api.PostForFile("/api/legacy-order/orders/" + HoApiClient.Seg(_store) + "/export", body, out suggested);
            });
            if (bytes == null) return;
            using (var dlg = new SaveFileDialog())
            {
                dlg.FileName = suggested;
                dlg.Filter = "Excel workbook (*.xlsx)|*.xlsx|Zip (*.zip)|*.zip|All files (*.*)|*.*";
                if (dlg.ShowDialog(this) == DialogResult.OK)
                {
                    File.WriteAllBytes(dlg.FileName, bytes);
                    lblstatus.Text = "Exported -> " + Path.GetFileName(dlg.FileName);
                }
            }
        }

        private void CompareSupplier()
        {
            MessageBox.Show(this, "Compare uses a previous order and runs in the Head Office console.",
                Ui.AppTitle, MessageBoxButtons.OK, MessageBoxIcon.Information);
        }

        // ------------------------------------------------------------------
        // helpers
        // ------------------------------------------------------------------
        private void ShowStoreList(bool show)
        {
            dgvStoreList.Visible = show;
            if (show) dgvStoreList.BringToFront();
        }

        private void ShowSupplierList(bool show)
        {
            dgvSupplierList.Visible = show;
            bool detail = !show;
            dgvPurchaseDetails.Visible = detail;
            dgvSalesDetails.Visible = detail;
            Chart1.Visible = detail;
            if (show) dgvSupplierList.BringToFront();
        }

        private void ClearDetails()
        {
            dgvPurchaseDetails.DataSource = null;
            dgvSalesDetails.DataSource = null;
            Chart1.Series.Clear();
        }

        private void MakeOrderQtyEditable()
        {
            foreach (DataGridViewColumn c in dgvMain.Columns)
                c.ReadOnly = !string.Equals(c.Name, "orderqty", StringComparison.OrdinalIgnoreCase);
        }

        private static double ParseNum(Dictionary<string, object> r, string key)
        {
            object v;
            if (r != null && r.TryGetValue(key, out v) && v != null)
            {
                double d;
                if (double.TryParse(Convert.ToString(v, CultureInfo.InvariantCulture),
                        NumberStyles.Any, CultureInfo.InvariantCulture, out d))
                    return d;
            }
            return 0;
        }

        private Label Lbl(string text, int x, int y)
        {
            var l = new Label();
            l.Text = text; l.AutoSize = true; l.BackColor = Color.Transparent;
            l.Font = LblFont; l.Location = new Point(x, y);
            return l;
        }

        private TextBox Txt(int x, int y, int w, int h)
        {
            var t = new TextBox();
            t.Location = new Point(x, y); t.Size = new Size(w, h);
            return t;
        }

        private ComboBox Combo(int x, int y, int w)
        {
            var c = new ComboBox();
            c.DropDownStyle = ComboBoxStyle.DropDownList;
            c.Location = new Point(x, y); c.Size = new Size(w, 21);
            return c;
        }

        private Button Btn(string text, int x, int y, int w, int h)
        {
            var b = new Button();
            b.Text = text; b.Location = new Point(x, y); b.Size = new Size(w, h);
            b.UseVisualStyleBackColor = true;
            return b;
        }

        private DataGridView Grid(int x, int y, int w, int h, bool readOnly)
        {
            var g = new DataGridView();
            g.Location = new Point(x, y); g.Size = new Size(w, h);
            g.ReadOnly = readOnly;
            g.AllowUserToAddRows = false;
            g.AllowUserToDeleteRows = false;
            g.AllowUserToResizeRows = false;
            g.Font = GridFont;
            g.SelectionMode = DataGridViewSelectionMode.FullRowSelect;
            g.MultiSelect = false;
            g.AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.DisplayedCells;
            g.BackgroundColor = Color.White;
            return g;
        }

        private static Image LoadBackground()
        {
            try
            {
                var asm = Assembly.GetExecutingAssembly();
                using (var st = asm.GetManifestResourceStream("NexoraOrderManagement.vb_bg.png"))
                    if (st != null) return Image.FromStream(st);
            }
            catch { }
            return null;
        }
    }
}
