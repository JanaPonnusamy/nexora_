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

        // Build a DataTable from API rows. A column whose every non-empty value
        // is numeric becomes a real numeric (double) column -- so whole numbers
        // render without a trailing ".0" (qty columns) and the grid can apply
        // N0/N2 cell formats. Everything else stays string.
        public static DataTable ToTable(List<Dictionary<string, object>> rows)
        {
            var table = new DataTable();
            var cols = new List<string>();
            foreach (var row in rows)
                foreach (var key in row.Keys)
                    if (!cols.Contains(key)) cols.Add(key);

            var numeric = new Dictionary<string, bool>();
            foreach (var c in cols)
            {
                bool anyVal = false, allNum = true;
                foreach (var row in rows)
                {
                    object v;
                    if (!row.TryGetValue(c, out v) || v == null) continue;
                    var sv = Convert.ToString(v, CultureInfo.InvariantCulture);
                    if (sv.Length == 0) continue;
                    anyVal = true;
                    if (!IsNumeric(v)) { allNum = false; break; }
                }
                numeric[c] = anyVal && allNum;
            }

            foreach (var c in cols)
                table.Columns.Add(c, numeric[c] ? typeof(double) : typeof(string));

            foreach (var row in rows)
            {
                var dr = table.NewRow();
                foreach (var c in cols)
                {
                    object v;
                    bool has = row.TryGetValue(c, out v) && v != null;
                    if (numeric[c])
                    {
                        double d;
                        if (has && double.TryParse(Convert.ToString(v, CultureInfo.InvariantCulture),
                                NumberStyles.Any, CultureInfo.InvariantCulture, out d))
                            dr[c] = d;
                        else dr[c] = DBNull.Value;
                    }
                    else dr[c] = has ? FormatValue(v) : "";
                }
                table.Rows.Add(dr);
            }
            return table;
        }

        private static bool IsNumeric(object v)
        {
            if (v is bool || v is DateTime) return false;
            if (v is int || v is long || v is short || v is byte ||
                v is double || v is float || v is decimal) return true;
            var s = v as string;
            if (s != null)
            {
                double d;
                return double.TryParse(s.Trim(), NumberStyles.Any, CultureInfo.InvariantCulture, out d);
            }
            return false;
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
