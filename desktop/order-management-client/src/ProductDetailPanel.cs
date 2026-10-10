using System;
using System.Drawing;
using System.Windows.Forms;

namespace NexoraOrderManagement
{
    // The right-hand product detail panel (as in the VB Form1): purchase, sales,
    // monthly stats and order history for whichever product is selected in
    // either screen. All four come from /qty-check/{store}/{code}/* .
    internal class ProductDetailPanel : UserControl
    {
        private readonly HoApiClient _api;
        private readonly Label _header;
        private readonly TabControl _tabs;
        private readonly DataGridView _gPurchase;
        private readonly DataGridView _gSales;
        private readonly DataGridView _gMonthly;
        private readonly DataGridView _gHistory;

        private string _store = "";

        public ProductDetailPanel(HoApiClient api)
        {
            _api = api;
            Dock = DockStyle.Fill;
            BackColor = Color.White;

            _header = new Label();
            _header.Dock = DockStyle.Top;
            _header.Height = 46;
            _header.Padding = new Padding(10, 8, 10, 8);
            _header.Font = new Font("Segoe UI", 10f, FontStyle.Bold);
            _header.Text = "Select a product to see its history";
            _header.BackColor = Color.FromArgb(31, 41, 55);
            _header.ForeColor = Color.White;
            _header.TextAlign = ContentAlignment.MiddleLeft;

            _tabs = new TabControl();
            _tabs.Dock = DockStyle.Fill;

            _gPurchase = Ui.NewGrid(true);
            _gSales = Ui.NewGrid(true);
            _gMonthly = Ui.NewGrid(true);
            _gHistory = Ui.NewGrid(true);

            _tabs.TabPages.Add(MakeTab("Purchase", _gPurchase));
            _tabs.TabPages.Add(MakeTab("Sales", _gSales));
            _tabs.TabPages.Add(MakeTab("Monthly", _gMonthly));
            _tabs.TabPages.Add(MakeTab("Order History", _gHistory));

            Controls.Add(_tabs);
            Controls.Add(_header);
        }

        private static TabPage MakeTab(string title, DataGridView grid)
        {
            var page = new TabPage(title);
            page.Padding = new Padding(2);
            grid.Dock = DockStyle.Fill;
            page.Controls.Add(grid);
            return page;
        }

        public void SetStore(string store)
        {
            _store = store == null ? "" : store;
            Clear();
        }

        public void Clear()
        {
            _header.Text = "Select a product to see its history";
            _gPurchase.DataSource = null;
            _gSales.DataSource = null;
            _gMonthly.DataSource = null;
            _gHistory.DataSource = null;
        }

        public void SetProduct(long productCode, string productName)
        {
            if (string.IsNullOrEmpty(_store) || productCode <= 0) { Clear(); return; }
            _header.Text = productName + "  (#" + productCode + ")";
            Ui.Guard(this, delegate
            {
                var baseP = "/api/legacy-order/qty-check/" + HoApiClient.Seg(_store) + "/" + productCode;
                _gPurchase.DataSource = Ui.ToTable(Json.Rows(_api.GetJson(baseP + "/purchase-details?mode=local")));
                _gSales.DataSource = Ui.ToTable(Json.Rows(_api.GetJson(baseP + "/sales-details?mode=local")));
                _gMonthly.DataSource = Ui.ToTable(Json.Rows(_api.GetJson(baseP + "/monthly-stats?mode=local")));
                _gHistory.DataSource = Ui.ToTable(Json.Rows(_api.GetJson(baseP + "/order-history")));
            });
        }
    }
}
