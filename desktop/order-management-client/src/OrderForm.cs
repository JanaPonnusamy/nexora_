using System;
using System.Collections.Generic;
using System.Data;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Windows.Forms;
using System.Windows.Forms.DataVisualization.Charting;

namespace NexoraOrderManagement
{
    // Replica of the VB.NET OrderManagement Form1 for the remote client: same
    // single-window layout, same controls/positions, same blue background and
    // monthly Purchase/Sales/Stock chart. Data comes only from the HO
    // /api/legacy-order/* API. This client exposes four read processes
    // (Pending Order Qty Check, Auto Pur UpDate, Order Based on Supplier Stock,
    // Supplier Order Details) and a single Export button -- no head-office
    // trigger buttons.
    internal class OrderForm : Form
    {
        private readonly HoApiClient _api;
        private readonly AppConfig _cfg;

        private Label lblExportStatus, lblSelectProcess, lblProductType, lblSupplierName, lblstatus;
        private TextBox txtStoreSearch, txtSupplierSearch;
        private ComboBox cboProcess, cboProductType;
        private DataGridView dgvMain, dgvStoreList, dgvSupplierList, dgvPurchaseDetails, dgvSalesDetails;
        private Chart Chart1;
        private Button btnExport;

        private string _store = "";
        private string _supplierCode = "";
        private string _supplierName = "";
        // Guards the detail/chart reload so it does not fire for every
        // SelectionChanged the grid raises while a large result set is binding
        // (that would be dozens of redundant 3-call detail fetches). We reload
        // the panel once, explicitly, after a bind settles.
        private bool _suppressDetail;

        private static readonly Font GridFont = new Font("Microsoft Sans Serif", 8.25f);
        private static readonly Font LblFont = new Font("Segoe UI", 10f, FontStyle.Bold);

        private const string PROC_QTY = "Pending Order Qty Check";
        private const string PROC_HIST = "Auto Pur UpDate";
        private const string PROC_STOCK = "Order Based on Supplier Stock";
        private const string PROC_ASSIGNED = "Supplier Order Details";

        // VB headerMap (merged from Form1.vb) -> friendly headers.
        private static readonly Dictionary<string, string> HeaderMap =
            new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            {"serialno","#"}, {"productname","Product Name"}, {"suppliername","Supplier Name"},
            {"orderqty","Or Qty"}, {"orgorderqty","Org Order Qty"}, {"orqty","Or Qty"},
            {"stockreceived","Recv Stock"}, {"rstock","RStock"}, {"freeqty","Free"}, {"free","Free"},
            {"totalstock","Stock"}, {"slsqty","Sls Qty"}, {"saleunit","Pack"}, {"maxsaleqty","Max Qty"},
            {"maxqty","Max Qty"}, {"productdesc","Pro Desc"}, {"unitdescription","Desc"},
            {"mrp","MRP"}, {"itemcost","Cost"}, {"ptr","PTR"}, {"purchaseprice","PTR"},
            {"transactiondate","Txn Date"}, {"lastreceiveddate","LR Date"}, {"lastsaledate","LS Date"},
            {"grndate","GRN Date"}, {"grnno","GRN No"}, {"wantedtype","Wanted"}, {"wanteddate","Wanted Date"},
            {"orsupplier","Or Supplier"}, {"orsuppliercode","Supplier Code"}, {"totalquantity","Qty"},
            {"bill_time","Bill Time"}, {"salesmanname","Salesman"}, {"customername","Customer"},
            {"type","Type"}, {"dis","Dis%"}, {"bnumber","Bill No"}, {"remarks","Remarks"},
            {"s_stock","S_Stock"}, {"sch","Sch"}, {"minqty","MinQty"}, {"producttypename","Category"},
            {"sublocation","Rack"}, {"rack","Rack"}, {"status","Status"}, {"discount","Dis%"},
            {"supplierproductcode","Sup Prod Code"}, {"supplierproductname","Sup Prod Name"},
        };

        private static readonly HashSet<string> PriceKeys =
            new HashSet<string>(StringComparer.OrdinalIgnoreCase) { "mrp", "itemcost", "ptr", "purchaseprice" };
        private static readonly HashSet<string> QtyKeys =
            new HashSet<string>(StringComparer.OrdinalIgnoreCase) {
                "orderqty","orgorderqty","orqty","stockreceived","rstock","freeqty","free","totalstock",
                "slsqty","saleunit","maxsaleqty","maxqty","productdesc","totalquantity","minqty","s_stock","sch" };

        public OrderForm(AppConfig cfg, HoApiClient api)
        {
            _cfg = cfg;
            _api = api;
            BuildUi();
            Load += delegate { InitData(); };
        }

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

            dgvMain = Grid(4, 36, 878, 648, false);
            dgvStoreList = Grid(102, 36, 245, 151, true);
            dgvSupplierList = Grid(838, 36, 518, 140, true); dgvSupplierList.Visible = false;
            dgvPurchaseDetails = Grid(886, 36, 468, 200, true);
            dgvSalesDetails = Grid(886, 240, 468, 200, true);

            Chart1 = new Chart();
            Chart1.Location = new Point(886, 440);
            Chart1.Size = new Size(468, 244);
            Chart1.BackColor = Color.White;

            btnExport = Btn("Export", 886, 689, 90, 26);
            lblstatus = Lbl("", 8, 692); lblstatus.Font = new Font("Segoe UI", 9f, FontStyle.Bold);

            Controls.Add(dgvMain);
            Controls.Add(dgvPurchaseDetails);
            Controls.Add(dgvSalesDetails);
            Controls.Add(Chart1);
            Controls.Add(dgvSupplierList);
            Controls.Add(dgvStoreList);
            foreach (Control c in new Control[] {
                lblExportStatus, txtStoreSearch, lblSelectProcess, cboProcess, lblProductType,
                cboProductType, lblSupplierName, txtSupplierSearch, btnExport, lblstatus })
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
            dgvMain.CellFormatting += DgvMain_CellFormatting;
            dgvMain.EditingControlShowing += DgvMain_EditingControlShowing;

            btnExport.Click += delegate { ExportGrid(); };
        }

        // ------------------------------------------------------------------
        private void InitData()
        {
            cboProcess.Items.Clear();
            cboProcess.Items.AddRange(new object[] { PROC_QTY, PROC_HIST, PROC_STOCK, PROC_ASSIGNED });
            cboProductType.Items.Clear();
            cboProductType.Items.AddRange(new object[] { "All", "Pharma", "Non Pharma" });
            cboProductType.SelectedIndex = 0;

            LoadStores();
            if (!_api.IsFullAccess && dgvStoreList.Rows.Count >= 1) PickStore(0);
            else ShowStoreList(true);
        }

        private void LoadStores()
        {
            Ui.Guard(this, delegate
            {
                List<Dictionary<string, object>> rows;
                if (_api.IsFullAccess)
                    rows = Json.Rows(_api.GetJson("/api/legacy-order/stores?active_only=true"));
                else
                {
                    rows = new List<Dictionary<string, object>>();
                    var d = new Dictionary<string, object>(); d["store_name"] = _api.StoreCode; rows.Add(d);
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

        private bool IsSupplierMode()
        {
            var p = cboProcess.Text;
            return p == PROC_HIST || p == PROC_STOCK || p == PROC_ASSIGNED;
        }

        private void LoadProcess()
        {
            if (string.IsNullOrEmpty(_store)) return;
            ClearDetails();
            dgvMain.DataSource = null;
            bool supplierMode = IsSupplierMode();
            lblSupplierName.Visible = supplierMode;
            txtSupplierSearch.Visible = supplierMode;
            if (supplierMode)
            {
                _supplierCode = ""; _supplierName = "";
                LoadSuppliers();
                ShowSupplierList(true);
                lblstatus.Text = "Pick a supplier for \"" + cboProcess.Text + "\"";
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
                        if (string.Equals(Json.Str(r, "producttypename"), type, StringComparison.OrdinalIgnoreCase)) f.Add(r);
                    rows = f;
                }
                _suppressDetail = true;
                try
                {
                    var table = Ui.ToTable(rows);
                    AddSerialNo(table);
                    dgvMain.DataSource = table;
                    ConfigureMainGrid(true);
                    lblstatus.Text = _store + " - Qty Check: " + rows.Count + " pending line(s)   (Enter = save, Esc = Don't Want)";
                    BeginQtyEdit();
                }
                finally { _suppressDetail = false; }
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
                dgvSupplierList.Columns["SupplierCode"].HeaderText = "Code";
                dgvSupplierList.Columns["SupplierName"].HeaderText = "Supplier Name";
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
            var proc = cboProcess.Text;
            Ui.Guard(this, delegate
            {
                string path;
                string what;
                if (proc == PROC_ASSIGNED)
                {
                    path = "/api/legacy-order/orders/" + HoApiClient.Seg(_store) +
                        "/assigned?supplier_code=" + HoApiClient.Qs(_supplierCode);
                    what = "placed-order line(s)";
                }
                else
                {
                    var mode = (proc == PROC_STOCK) ? "stock" : "history";
                    path = "/api/legacy-order/orders/" + HoApiClient.Seg(_store) +
                        "/by-supplier?supplier_code=" + HoApiClient.Qs(_supplierCode) + "&mode=" + mode;
                    what = "orderable line(s) [" + mode + "]";
                }
                var rows = Json.Rows(_api.GetJson(path));
                _suppressDetail = true;
                try
                {
                    var table = Ui.ToTable(rows);
                    AddSerialNo(table);
                    dgvMain.DataSource = table;
                    ConfigureMainGrid(false);
                    lblstatus.Text = _supplierName + ": " + rows.Count + " " + what;
                }
                finally { _suppressDetail = false; }
            });
            LoadDetailsForCurrent();
        }

        private void LoadDetailsForCurrent()
        {
            if (_suppressDetail) return;
            if (dgvMain.CurrentRow == null || string.IsNullOrEmpty(_store)) return;
            var code = Ui.ParseLong(Ui.RowValue(dgvMain, dgvMain.CurrentRow, "ProductCode", "productcode"));
            if (code <= 0) return;
            Ui.Guard(this, delegate
            {
                var baseP = "/api/legacy-order/qty-check/" + HoApiClient.Seg(_store) + "/" + code;
                dgvPurchaseDetails.DataSource = Ui.ToTable(Json.Rows(_api.GetJson(baseP + "/purchase-details?mode=local")));
                ConfigureDetailGrid(dgvPurchaseDetails);
                dgvSalesDetails.DataSource = Ui.ToTable(Json.Rows(_api.GetJson(baseP + "/sales-details?mode=local")));
                ConfigureDetailGrid(dgvSalesDetails);
                BuildChart(Json.Rows(_api.GetJson(baseP + "/monthly-stats?mode=local")),
                    Ui.RowValue(dgvMain, dgvMain.CurrentRow, "ProductName", "productname"));
            });
        }

        // ------------------------------------------------------------------
        // monthly Purchase/Sales/Stock column chart (same colors as VB)
        private void BuildChart(List<Dictionary<string, object>> rows, string productName)
        {
            Chart1.Series.Clear(); Chart1.ChartAreas.Clear(); Chart1.Legends.Clear(); Chart1.Titles.Clear();
            Chart1.ChartAreas.Add(new ChartArea("ca"));
            Chart1.Titles.Add("Monthly Statistics - " + productName);
            AddSeries(rows, "Purchase", "purchase", Color.Blue);
            AddSeries(rows, "Sales", "sales", Color.Green);
            AddSeries(rows, "Stock", "stock", Color.Red);
            var legend = new Legend("legend"); legend.Docking = Docking.Bottom;
            Chart1.Legends.Add(legend);
        }

        private void AddSeries(List<Dictionary<string, object>> rows, string name, string key, Color color)
        {
            var s = new Series(name); s.ChartType = SeriesChartType.Column; s.Color = color;
            foreach (var r in rows) s.Points.AddXY(Json.Str(r, "month"), ParseNum(r, key));
            Chart1.Series.Add(s);
        }

        // ------------------------------------------------------------------
        // OrderQty edit: Enter commits the typed value, Esc = "Don't Want" (0).
        private void DgvMain_EditingControlShowing(object sender, DataGridViewEditingControlShowingEventArgs e)
        {
            var tb = e.Control as TextBox;
            if (tb == null) return;
            tb.KeyDown -= OrderQtyEditKeyDown;
            tb.KeyDown += OrderQtyEditKeyDown;
        }

        private void OrderQtyEditKeyDown(object sender, KeyEventArgs e)
        {
            if (cboProcess.Text != PROC_QTY) return;
            if (e.KeyCode == Keys.Escape)
            {
                var tb = sender as TextBox;
                if (tb != null) tb.Text = "0";     // "Don't Want to Order"
                e.Handled = true; e.SuppressKeyPress = true;
                dgvMain.EndEdit();                 // commit -> CellEndEdit with 0
            }
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

        // paint the OrderQty column green (highest precedence, overrides alt rows)
        private void DgvMain_CellFormatting(object sender, DataGridViewCellFormattingEventArgs e)
        {
            if (e.ColumnIndex < 0) return;
            if (string.Equals(dgvMain.Columns[e.ColumnIndex].Name, "orderqty", StringComparison.OrdinalIgnoreCase))
                e.CellStyle.BackColor = Color.LightGreen;
        }

        private void BeginQtyEdit()
        {
            var col = FindColumn(dgvMain, "orderqty");
            if (col == null || dgvMain.Rows.Count == 0) return;
            try
            {
                dgvMain.CurrentCell = dgvMain.Rows[0].Cells[col.Index];
                dgvMain.Focus();
                BeginInvoke(new MethodInvoker(delegate { try { dgvMain.BeginEdit(true); } catch { } }));
            }
            catch { }
        }

        // ------------------------------------------------------------------
        // Export: the current grid (Excel-openable CSV). Works for every view,
        // including an already-placed Supplier Order Details order.
        private void ExportGrid()
        {
            if (dgvMain.DataSource == null || dgvMain.Rows.Count == 0) { lblstatus.Text = "Nothing to export"; return; }
            var cols = new List<DataGridViewColumn>();
            foreach (DataGridViewColumn c in dgvMain.Columns) if (c.Visible) cols.Add(c);
            cols.Sort(delegate(DataGridViewColumn a, DataGridViewColumn b) { return a.DisplayIndex.CompareTo(b.DisplayIndex); });

            using (var dlg = new SaveFileDialog())
            {
                dlg.Filter = "CSV (Excel) (*.csv)|*.csv|All files (*.*)|*.*";
                dlg.FileName = ExportName();
                if (dlg.ShowDialog(this) != DialogResult.OK) return;
                var sb = new StringBuilder();
                sb.AppendLine(string.Join(",", cols.Select(delegate(DataGridViewColumn c) { return Csv(c.HeaderText); }).ToArray()));
                int n = 0;
                foreach (DataGridViewRow r in dgvMain.Rows)
                {
                    if (r.IsNewRow) continue;
                    sb.AppendLine(string.Join(",", cols.Select(delegate(DataGridViewColumn c)
                    {
                        var fv = r.Cells[c.Index].FormattedValue;
                        return Csv(fv == null ? "" : fv.ToString());
                    }).ToArray()));
                    n++;
                }
                File.WriteAllText(dlg.FileName, sb.ToString(), Encoding.UTF8);
                lblstatus.Text = "Exported " + n + " row(s) -> " + Path.GetFileName(dlg.FileName);
            }
        }

        private string ExportName()
        {
            var parts = new List<string>();
            parts.Add(_store);
            parts.Add(cboProcess.Text.Replace(" ", ""));
            if (_supplierName.Length > 0) parts.Add(_supplierName);
            parts.Add(DateTime.Now.ToString("yyyyMMdd-HHmm"));
            var name = string.Join("_", parts.ToArray());
            foreach (var ch in Path.GetInvalidFileNameChars()) name = name.Replace(ch, '_');
            return name + ".csv";
        }

        private static string Csv(string s)
        {
            if (s == null) return "";
            if (s.IndexOf(',') >= 0 || s.IndexOf('"') >= 0 || s.IndexOf('\n') >= 0 || s.IndexOf('\r') >= 0)
                return "\"" + s.Replace("\"", "\"\"") + "\"";
            return s;
        }

        // ------------------------------------------------------------------
        // grid configuration (VB headers, formats, hidden productcode, styling)
        private void ConfigureMainGrid(bool qtyEditable)
        {
            dgvMain.EnableHeadersVisualStyles = false;
            dgvMain.ColumnHeadersDefaultCellStyle.BackColor = Color.LightSteelBlue;
            dgvMain.ColumnHeadersDefaultCellStyle.Font = new Font("Segoe UI", 10f, FontStyle.Bold);
            dgvMain.ColumnHeadersDefaultCellStyle.Alignment = DataGridViewContentAlignment.MiddleCenter;
            dgvMain.AlternatingRowsDefaultCellStyle.BackColor = Color.LightCyan;
            dgvMain.DefaultCellStyle.SelectionBackColor = Color.LightGreen;
            dgvMain.RowTemplate.Height = 24;

            foreach (DataGridViewColumn col in dgvMain.Columns)
            {
                var key = col.Name.ToLowerInvariant();
                col.HeaderText = Header(col.Name);
                ApplyNumberFormat(col, key);
                if (key == "productcode") col.Visible = false;
                col.ReadOnly = !(qtyEditable && key == "orderqty");
                if (key == "serialno") col.Width = 34;
            }
        }

        private void ConfigureDetailGrid(DataGridView dgv)
        {
            dgv.EnableHeadersVisualStyles = false;
            dgv.ColumnHeadersDefaultCellStyle.BackColor = Color.LightSteelBlue;
            dgv.ColumnHeadersDefaultCellStyle.Font = new Font("Segoe UI", 8.5f, FontStyle.Bold);
            dgv.AlternatingRowsDefaultCellStyle.BackColor = Color.LightCyan;
            foreach (DataGridViewColumn col in dgv.Columns)
            {
                var key = col.Name.ToLowerInvariant();
                col.HeaderText = Header(col.Name);
                ApplyNumberFormat(col, key);
                if (key == "productcode") col.Visible = false;
            }
        }

        private static void ApplyNumberFormat(DataGridViewColumn col, string key)
        {
            if (PriceKeys.Contains(key))
            {
                col.DefaultCellStyle.Format = "N2";
                col.DefaultCellStyle.Alignment = DataGridViewContentAlignment.MiddleRight;
            }
            else if (QtyKeys.Contains(key))
            {
                col.DefaultCellStyle.Format = "N0";
                col.DefaultCellStyle.Alignment = DataGridViewContentAlignment.MiddleRight;
            }
        }

        private static string Header(string colName)
        {
            string h;
            if (HeaderMap.TryGetValue(colName.ToLowerInvariant(), out h)) return h;
            return CultureInfo.CurrentCulture.TextInfo.ToTitleCase(colName.ToLowerInvariant());
        }

        private static void AddSerialNo(DataTable table)
        {
            if (table.Columns.Contains("SerialNo")) return;
            var c = new DataColumn("SerialNo", typeof(int));
            table.Columns.Add(c);
            c.SetOrdinal(0);
            for (int i = 0; i < table.Rows.Count; i++) table.Rows[i]["SerialNo"] = i + 1;
            table.AcceptChanges();
        }

        // ------------------------------------------------------------------
        private void ShowStoreList(bool show) { dgvStoreList.Visible = show; if (show) dgvStoreList.BringToFront(); }

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

        private static DataGridViewColumn FindColumn(DataGridView g, string name)
        {
            foreach (DataGridViewColumn c in g.Columns)
                if (string.Equals(c.Name, name, StringComparison.OrdinalIgnoreCase)) return c;
            return null;
        }

        private static double ParseNum(Dictionary<string, object> r, string key)
        {
            object v;
            if (r != null && r.TryGetValue(key, out v) && v != null)
            {
                double d;
                if (double.TryParse(Convert.ToString(v, CultureInfo.InvariantCulture),
                        NumberStyles.Any, CultureInfo.InvariantCulture, out d)) return d;
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

        private TextBox Txt(int x, int y, int w, int h) { var t = new TextBox(); t.Location = new Point(x, y); t.Size = new Size(w, h); return t; }

        private ComboBox Combo(int x, int y, int w)
        {
            var c = new ComboBox(); c.DropDownStyle = ComboBoxStyle.DropDownList;
            c.Location = new Point(x, y); c.Size = new Size(w, 21); return c;
        }

        private Button Btn(string text, int x, int y, int w, int h)
        {
            var b = new Button(); b.Text = text; b.Location = new Point(x, y); b.Size = new Size(w, h);
            b.UseVisualStyleBackColor = true; b.Font = new Font("Segoe UI", 9f, FontStyle.Bold);
            return b;
        }

        private DataGridView Grid(int x, int y, int w, int h, bool readOnly)
        {
            var g = new DataGridView();
            g.Location = new Point(x, y); g.Size = new Size(w, h);
            g.ReadOnly = readOnly;
            g.AllowUserToAddRows = false; g.AllowUserToDeleteRows = false; g.AllowUserToResizeRows = false;
            g.Font = GridFont;
            g.SelectionMode = DataGridViewSelectionMode.FullRowSelect; g.MultiSelect = false;
            g.AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.DisplayedCells;
            g.BackgroundColor = Color.White;
            g.EditMode = DataGridViewEditMode.EditOnKeystrokeOrF2;
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
