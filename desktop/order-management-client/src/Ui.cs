using System;
using System.Collections.Generic;
using System.Data;
using System.Drawing;
using System.Globalization;
using System.Windows.Forms;

namespace NexoraOrderManagement
{
    internal static class Ui
    {
        public const string AppTitle = "Nexora Order Management";

        // Run a bit of work under a wait cursor, turning any API/other error into
        // a tidy message box instead of a crash.
        public static void Guard(IWin32Window owner, Action work)
        {
            try
            {
                Cursor.Current = Cursors.WaitCursor;
                work();
            }
            catch (ApiException ex)
            {
                var extra = ex.StatusCode == 401
                    ? "\n\nYour session may have been taken over by another sign-in. Restart and log in again."
                    : "";
                MessageBox.Show(owner, ex.Message + " (HTTP " + ex.StatusCode + ")" + extra,
                    AppTitle, MessageBoxButtons.OK, MessageBoxIcon.Warning);
            }
            catch (Exception ex)
            {
                MessageBox.Show(owner, ex.Message, AppTitle, MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
            finally
            {
                Cursor.Current = Cursors.Default;
            }
        }

        public static DataGridView NewGrid(bool readOnly)
        {
            var g = new DataGridView();
            g.Dock = DockStyle.Fill;
            g.ReadOnly = readOnly;
            g.AllowUserToAddRows = false;
            g.AllowUserToDeleteRows = false;
            g.AllowUserToResizeRows = false;
            g.RowHeadersVisible = false;
            g.SelectionMode = DataGridViewSelectionMode.FullRowSelect;
            g.MultiSelect = false;
            g.AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.DisplayedCells;
            g.BackgroundColor = Color.White;
            g.BorderStyle = BorderStyle.None;
            g.EnableHeadersVisualStyles = true;
            g.ColumnHeadersHeightSizeMode = DataGridViewColumnHeadersHeightSizeMode.DisableResizing;
            g.AlternatingRowsDefaultCellStyle.BackColor = Color.FromArgb(245, 247, 250);
            return g;
        }

        // Build an all-string DataTable from API rows; column order follows the
        // first row, with any later-appearing keys appended.
        public static DataTable ToTable(List<Dictionary<string, object>> rows)
        {
            var table = new DataTable();
            var cols = new List<string>();
            foreach (var row in rows)
                foreach (var key in row.Keys)
                    if (!cols.Contains(key)) cols.Add(key);
            foreach (var c in cols) table.Columns.Add(c, typeof(string));
            foreach (var row in rows)
            {
                var dr = table.NewRow();
                foreach (var c in cols)
                {
                    object v;
                    dr[c] = (row.TryGetValue(c, out v) && v != null) ? FormatValue(v) : "";
                }
                table.Rows.Add(dr);
            }
            return table;
        }

        public static string FormatValue(object v)
        {
            if (v == null) return "";
            if (v is bool) return ((bool)v) ? "Yes" : "No";
            if (v is DateTime)
                return ((DateTime)v).ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
            return Convert.ToString(v, CultureInfo.InvariantCulture);
        }

        // Read a cell by any of the candidate column names (case-insensitive) --
        // the API mixes PascalCase (ProductCode) and lowercase (productcode)
        // across endpoints.
        public static string RowValue(DataGridView g, DataGridViewRow row, params string[] names)
        {
            if (g == null || row == null) return "";
            foreach (DataGridViewColumn col in g.Columns)
                foreach (var n in names)
                    if (string.Equals(col.Name, n, StringComparison.OrdinalIgnoreCase))
                    {
                        var c = row.Cells[col.Index].Value;
                        return c == null ? "" : c.ToString();
                    }
            return "";
        }

        public static long ParseLong(string s)
        {
            long v;
            s = (s == null ? "" : s.Trim());
            // tolerate "123.0" style numbers that arrive as floats
            double d;
            if (long.TryParse(s, out v)) return v;
            if (double.TryParse(s, NumberStyles.Any, CultureInfo.InvariantCulture, out d)) return (long)d;
            return 0;
        }

        public static int ParseInt(string s)
        {
            return (int)ParseLong(s);
        }
    }
}
