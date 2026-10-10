using System;
using System.Data;
using System.Drawing;
using System.Windows.Forms;

namespace NexoraOrderManagement
{
    // "Pending Order Qty Check" -- the rows not yet reviewed (qtycheck=0,
    // status=0). The user edits OrderQty inline (Enter commits) or marks a line
    // "don't want" (sets 0); either way the line is reviewed and drops off the
    // grid, exactly as the VB Qty Check screen behaved.
    internal class QtyCheckView : UserControl
    {
        private readonly HoApiClient _api;
        private readonly DataGridView _grid;
        private readonly Label _status;
        private string _store = "";

        public event ProductSelectedHandler ProductSelected;

        public QtyCheckView(HoApiClient api)
        {
            _api = api;
            Dock = DockStyle.Fill;
            BackColor = Color.White;

            var bar = new FlowLayoutPanel();
            bar.Dock = DockStyle.Top;
            bar.Height = 40;
            bar.Padding = new Padding(6, 6, 6, 6);
            bar.FlowDirection = FlowDirection.LeftToRight;

            var refresh = new Button();
            refresh.Text = "Refresh";
            refresh.AutoSize = true;
            refresh.Click += delegate { Reload(); };

            var dontWant = new Button();
            dontWant.Text = "Mark \"Don't Want\" (0)";
            dontWant.AutoSize = true;
            dontWant.Click += delegate { MarkDontWant(); };

            _status = new Label();
            _status.AutoSize = true;
            _status.Padding = new Padding(10, 8, 0, 0);
            _status.Text = "";

            bar.Controls.Add(refresh);
            bar.Controls.Add(dontWant);
            bar.Controls.Add(_status);

            _grid = Ui.NewGrid(false);   // editable: only OrderQty, enforced below
            _grid.DataBindingComplete += Grid_DataBindingComplete;
            _grid.CellEndEdit += Grid_CellEndEdit;
            _grid.SelectionChanged += delegate { RaiseSelected(); };

            Controls.Add(_grid);
            Controls.Add(bar);
        }

        public void LoadStore(string store)
        {
            _store = store == null ? "" : store;
            Reload();
        }

        public void Reload()
        {
            if (string.IsNullOrEmpty(_store)) return;
            Ui.Guard(this, delegate
            {
                var rows = Json.Rows(_api.GetJson("/api/legacy-order/qty-check/" + HoApiClient.Seg(_store)));
                _grid.DataSource = Ui.ToTable(rows);
                _status.Text = rows.Count + " line(s) pending review";
            });
            RaiseSelected();
        }

        private void Grid_DataBindingComplete(object sender, DataGridViewBindingCompleteEventArgs e)
        {
            // Lock every column, then re-open just OrderQty for editing.
            foreach (DataGridViewColumn c in _grid.Columns)
                c.ReadOnly = !string.Equals(c.Name, "orderqty", StringComparison.OrdinalIgnoreCase);
        }

        private void Grid_CellEndEdit(object sender, DataGridViewCellEventArgs e)
        {
            if (e.RowIndex < 0 || e.ColumnIndex < 0) return;
            var col = _grid.Columns[e.ColumnIndex];
            if (!string.Equals(col.Name, "orderqty", StringComparison.OrdinalIgnoreCase)) return;

            var row = _grid.Rows[e.RowIndex];
            var code = Ui.ParseLong(Ui.RowValue(_grid, row, "productcode", "ProductCode"));
            var qty = Ui.ParseInt(Convert.ToString(row.Cells[e.ColumnIndex].Value));
            if (code <= 0) return;

            Ui.Guard(this, delegate
            {
                var body = "{\"order_qty\": " + qty + "}";
                var res = Json.Obj(_api.Patch(
                    "/api/legacy-order/qty-check/" + HoApiClient.Seg(_store) + "/" + code, body));
                _status.Text = "Reviewed #" + code + " -> " + qty +
                    " (" + Json.Str(res, "remarks") + ")";
                // Reviewed lines leave the pending grid.
                RemoveCurrentRow(e.RowIndex);
            });
        }

        private void MarkDontWant()
        {
            if (_grid.CurrentRow == null) return;
            var rowIndex = _grid.CurrentRow.Index;
            var code = Ui.ParseLong(Ui.RowValue(_grid, _grid.CurrentRow, "productcode", "ProductCode"));
            if (code <= 0) return;
            Ui.Guard(this, delegate
            {
                var res = Json.Obj(_api.Patch(
                    "/api/legacy-order/qty-check/" + HoApiClient.Seg(_store) + "/" + code,
                    "{\"order_qty\": 0}"));
                _status.Text = "Marked #" + code + " \"don't want\" (" + Json.Str(res, "remarks") + ")";
                RemoveCurrentRow(rowIndex);
            });
        }

        private void RemoveCurrentRow(int rowIndex)
        {
            var table = _grid.DataSource as DataTable;
            if (table != null && rowIndex >= 0 && rowIndex < table.Rows.Count)
            {
                table.Rows[rowIndex].Delete();
                table.AcceptChanges();
                _status.Text = table.Rows.Count + " line(s) pending review";
            }
        }

        private void RaiseSelected()
        {
            if (ProductSelected == null || _grid.CurrentRow == null) return;
            var code = Ui.ParseLong(Ui.RowValue(_grid, _grid.CurrentRow, "productcode", "ProductCode"));
            var name = Ui.RowValue(_grid, _grid.CurrentRow, "productname", "ProductName");
            if (code > 0) ProductSelected(code, name);
        }
    }
}
