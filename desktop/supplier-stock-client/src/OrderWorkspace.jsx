import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { api } from './api/client.js';
import { AbnormalMark, AbnormalSalesStrip, useAbnormalSales } from './abnormalSales.jsx';
import { OwBulkAssign } from './bulkAssign.jsx';
import { WhatsAppSendDialog, storeWhatsAppAvailable } from './storeWhatsApp.jsx';
import {
  OW_EXPORT_COLUMN_DEFS,
  OW_GEAR_PATH,
  OwExportCard,
  OwGridSettings,
  OwSupplierPicker,
  healColOrder,
  orderOwKeys,
  resolveOwColumns,
} from './OwSharedControls.jsx';
import {
  asArray,
  fmtOwDate,
  fmtOwMoney,
  fmtOwPct,
  fmtOwQty,
  fmtOwSigned,
} from './OwFormatters.js';
import { OwDocumentCard } from './OwDocumentCard.jsx';
import { OrderIntelligence } from './OwIntelligencePanel.jsx';
import {
  owDefaultExportSettings,
  owExportDateFolder,
  owSafeFileName,
  owSafePathSegment,
  owSaveExport,
  readOwExportSettings,
  writeOwExportSettings,
} from './OwExportKit.js';
import {
  owLineFromRow,
  owLineNote,
  owNormalizeLayout,
  owWorkspaceSummary,
} from './orderWorkspaceView.js';

// Order Workspace component, extracted from App.jsx (NEXORA MEDIQ Phase 4
// structural refactor, see docs/NEXORA_MEDIQ_AUDIT/22_PHASE4_ORDER_WORKSPACE_EXTRACTION_REPORT.md
// and 23_PHASE4_COMPLETION_AND_VALIDATION_REPORT.md). No behavior changed in
// the move -- this is the exact code that lived inline in App.jsx, now its
// own module.

// Dev-only: when running under `vite` with VITE_DEV_STORE set, the Order
// Workspace auto-selects that store name instead of the last-remembered one.
// Stripped from any packaged installer, same pattern as App.jsx's own
// DEV_AUTO_LOGIN_USER/PASS.
const DEV_STORE = import.meta.env.DEV ? (import.meta.env.VITE_DEV_STORE || '') : '';

// ---- Order Workspace grid column model + per-grid settings ----
// Each grid (Qty Review, Review All) has its own column list; users can hide,
// reorder and resize columns via a modern settings card, persisted per grid.
const OW_QTY_COLUMNS = [
  { key: 'sno', label: 'S.No', width: 56, align: 'right', locked: true },
  { key: 'name', label: 'Product Name', width: 160, locked: true },
  { key: 'offer', label: '🎁', width: 22, align: 'right' },
  // 84px fit only the qty input itself (54px) -- the diff-arrow slot next to
  // it (.ow-qty-diff-slot, fixed 3.6rem/~58px, reserved even when empty) then
  // had nowhere to render but outside the column's own <colgroup> boundary.
  // Under the old percentage-stretched layout that overflow was invisible
  // (every column got far more real pixels than its weight implied); once
  // columns were switched to tight px widths (see owColgroupPct) the spill
  // became a visible black/empty bar bleeding into Stock. 116px actually
  // contains input+gap+diff-slot.
  { key: 'qtycheckstatus', label: 'QCheck', width: 58 },
  { key: 'orqty', label: 'Or Qty', width: 116, align: 'right', locked: true },
  { key: 'stock', label: 'Stock', width: 54, align: 'right' },
  { key: 'pack', label: 'Pack', width: 46, align: 'right' },
  { key: 'desc', label: 'Desc', width: 56 },
  { key: 'slsqty', label: 'Sls Qty', width: 56, align: 'right' },
  { key: 'mrp', label: 'MRP', width: 60, align: 'right' },
  { key: 'lrdate', label: 'LRD', width: 44, align: 'right' },
  { key: 'lsdate', label: 'LSD', width: 44, align: 'right' },
  { key: 'maxqty', label: 'Max Qty', width: 56, align: 'right' },
  { key: 'wanted', label: 'Wanted', width: 116 }
];
const OW_REVIEW_COLUMNS = [
  { key: 'sno', label: 'S.No', width: 56, align: 'right', locked: true },
  { key: 'name', label: 'Product Name', width: 140, locked: true },
  { key: 'offer', label: '🎁', width: 22, align: 'right' },
  // 84px fit only the qty input itself (54px) -- the diff-arrow slot next to
  // it (.ow-qty-diff-slot, fixed 3.6rem/~58px, reserved even when empty) then
  // had nowhere to render but outside the column's own <colgroup> boundary.
  // Under the old percentage-stretched layout that overflow was invisible
  // (every column got far more real pixels than its weight implied); once
  // columns were switched to tight px widths (see owColgroupPct) the spill
  // became a visible black/empty bar bleeding into Stock. 116px actually
  // contains input+gap+diff-slot.
  { key: 'qtycheckstatus', label: 'QCheck', width: 58 },
  { key: 'orqty', label: 'Or Qty', width: 116, align: 'right', locked: true },
  { key: 'stock', label: 'Stock', width: 54, align: 'right' },
  { key: 'pack', label: 'Pack', width: 46, align: 'right' },
  { key: 'desc', label: 'Desc', width: 56 },
  { key: 'sls', label: 'Sls Qty', width: 54, align: 'right' },
  { key: 'mrp', label: 'MRP', width: 60, align: 'right' },
  { key: 'wanted', label: 'Wanted', width: 116 }
];

// Pending / By Supplier / Assigned share the same column widths as Qty Check
// for every column they have in common (spec: "all follow qty check column
// pattern") -- derived from OW_QTY_COLUMNS itself so the weights can never
// drift out of sync when that array changes. The offer gift icon is its OWN
// column again (owner ruling 2026-10-17: keep it separate, don't merge into
// the Or Qty cell -- an earlier attempt at that caused real visual bugs, a
// box-shadow "halo" meant to make the badge readable bled past its own flex
// slot and rendered on top of the Or Qty input next to it).
const OW_SHARED_SPINE = OW_QTY_COLUMNS.filter((c) => ['sno', 'name', 'offer', 'orqty', 'stock', 'pack', 'desc', 'slsqty', 'mrp'].includes(c.key));
const OW_WANTED_COL = { key: 'wanted', label: 'Wanted', width: 116 };
const OW_PENDING_COLUMNS = [...OW_SHARED_SPINE, { key: 'qtycheckstatus', label: 'QCheck', width: 58 }, { key: 'maxqty', label: 'Max Qty', width: 56 }, OW_WANTED_COL];
const OW_SUPPLIER_STOCK_EXTRA = [
  { key: 'sstock', label: 'S.Stock', width: 44, align: 'right' },
  { key: 'disc', label: 'Disc', width: 44, align: 'right' },
  { key: 'minqty', label: 'MinQty', width: 44, align: 'right' },
  { key: 'rack', label: 'Rack', width: 56 }
];
const OW_ACTION_COL = { key: 'action', label: 'Action', width: 140 };
// The By Supplier grid carries one extra column the other grids don't -- a
// narrow "already qty-checked" (✓) marker between Product Name and Or Qty.
// It MUST be represented in the colgroup too: a <colgroup> with fewer <col>
// than the table has columns leaves the trailing columns with no width under
// table-layout:fixed, which is what made the right-hand columns overlap.
const OW_CHECK_COL = { key: 'check', label: '✓', width: 22, align: 'right' };
// Labeled QTY CHECK status (Checked / Pending / Unknown), distinct from the
// ✓ icon column above -- owner explicitly asked to ADD this, not replace the
// existing checkmark. In By Supplier it sits right before Or Qty, matching
// the request ("beside product name, preferably before OR QTY"); in
// Assigned (Supplier Order Details) it sits right before Remarks (owner
// request). Source of truth is the SAME OrderManagement.Qtycheck field the
// ✓ column already reads (see owQtyCheckStatus) -- there is no separate
// persisted "result" to check, so this is a second view of the identical
// authoritative value, not a new data source.
const OW_QTYCHECK_STATUS_COL = { key: 'qtycheckstatus', label: 'QCheck', width: 58 };
// Authoritative Qty Check status -- STRICTLY server-persisted (repository.
// update_qty_check sets OrderManagement.Qtycheck=1 only on a genuine saved
// commit; see that function's docstring). Deliberately does NOT fold in
// qtyCheckedHere (the ✓ icon's local "treat as reviewed this session" set,
// which fires optimistically before any save round-trip confirms it
// persisted) -- per spec, Checked must mean "a valid result has been
// saved," not "the operator touched this row a moment ago." Qtycheck is a
// nullable BIT DEFAULT 0 (verified against the live schema): a genuinely
// untouched/new row reads 0 ("Pending"); only NULL/undefined (never
// observed in practice, but the column DOES allow it) falls through to
// "Unknown" rather than being silently treated as Pending OR Checked --
// this is the smallest safe handling for a value that can't be reliably
// classified, not an invented third state.
function owQtyCheckStatus(row) {
  const raw = row?.Qtycheck;
  if (raw === null || raw === undefined) return 'unknown';
  return Number(raw) === 1 ? 'checked' : 'pending';
}
const OW_QTYCHECK_STATUS_LABEL = { checked: 'Checked', pending: 'Pending', unknown: 'Unknown' };
// Supplier dropped -- the operator already picked it in the toolbar above
// (SUPPLIER: ...), so repeating the SAME name on every row of a supplier-
// scoped grid was pure redundancy, not information.
const OW_ASSIGNED_COLUMNS = [...OW_SHARED_SPINE, OW_WANTED_COL, OW_QTYCHECK_STATUS_COL, { key: 'remarks', label: 'Remarks', width: 150 }, OW_ACTION_COL];
function owSupplierColumns(stockMode) {
  const [sno, name, offer, orqty, stock, ...afterStock] = OW_SHARED_SPINE; // afterStock: [pack, desc, slsqty, mrp]
  // Live Stock mode: S.Stock (the SUPPLIER's own stock) sits immediately
  // after the main Stock column (owner request -- previously it was tacked
  // on at the end, after MRP, far from the column it needs to be visually
  // compared against). History mode never shows S.Stock at all (no
  // SupplierStock join in that query), so this split only matters for
  // stockMode=true; the shape otherwise matches owSupplierColumns' old
  // single `spine` construction.
  const [sstock, ...restExtra] = OW_SUPPLIER_STOCK_EXTRA; // [disc, minqty, rack]
  const spine = [sno, name, offer, OW_CHECK_COL, OW_QTYCHECK_STATUS_COL, orqty, stock];
  return stockMode
    ? [...spine, sstock, ...afterStock, ...restExtra, OW_WANTED_COL, OW_ACTION_COL]
    : [...spine, ...afterStock, OW_WANTED_COL, OW_ACTION_COL];
}

// Column "width" is a relative weight, not a literal pixel size: every <col>
// gets a percentage of the table (width / sum-of-all-widths), so Product
// Name's share stays proportional -- and therefore capped -- at every
// viewport size instead of soaking up 100% of whatever space the other
// (genuinely fixed-content) columns leave behind.
// Fixed px widths (not a % share of the container) -- a % share under
// table-layout:fixed always stretches every column to fill the container's
// full width, which on a wide screen inflates the gap between e.g. OR QTY
// and STOCK far past what their content needs (reported: compare against
// the legacy VB.NET grid, whose columns stay content-width regardless of
// window size). .ow-cfg/.ow-fixed now size the table itself to max-content
// (see styles.css) so these px widths are the table's real width, with any
// leftover container space left blank after the last column instead of
// being redistributed into every column.
function owColgroupPct(cols) {
  return cols.map((c) => <col key={c.key} style={{ width: `${Number(c.width) || 0}px` }} />);
}

// Columns that can't usefully be text-filtered (an icon/checkbox/action
// column) -- same across every grid this renders for, so one skip-list.
const OW_UNFILTERABLE_COLS = new Set(['sno', 'check', 'action', 'qtycheckstatus']);
// Columns whose real-world values are a small, known set -- these get a
// <select> in the filter row instead of a free-text box, since there's
// nothing meaningful to type ("yes"/"no" into a text box for a Yes/No column
// isn't a real filter). 'wanted' draws its options from the grid's own
// distinct values (wantedOptions); 'offer' is a fixed Offer/Non-Offer/All --
// it's a plain boolean, there's no dynamic value set to compute.
const OW_OFFER_FILTER_OPTIONS = [{ value: 'yes', label: 'Offer' }, { value: 'no', label: 'Non-Offer' }];
// Single shared class-decision function for BOTH the <th> (header) and <td>
// (body) of a given column -- see owBodyCellClass below, which calls this
// same logic rather than duplicating the key checks. 'orqty' gets its own
// ow-orqty-col marker so styles.css can carve it out of .ow-num's width:1%
// override (see that rule's comment): th and td must agree on this column's
// width, and the only way to guarantee that is for both to share the exact
// same className list, not just the same align/width NUMBERS.
function owHeaderClass(key, align) {
  const base = align === 'right' ? 'ow-num' : '';
  const withOrqty = key === 'orqty' ? `${base} ow-orqty-col`.trim() : base;
  return (key === 'offer' || key === 'check' ? `${withOrqty} ow-icon-th` : withOrqty) || undefined;
}
// The OR QTY column's body cell is NOT simply "right-aligned text" -- it's
// an input (~54px) plus an always-reserved diff-arrow slot (~58px) to its
// right, laid out flex-end (.ow-qty-cell/.ow-qty-diff-slot in styles.css).
// That pushes the input itself left-of-the-column's true center, while a
// plain right-aligned/centered header label sits over the WHOLE column
// (input + diff-slot) -- a real, measurable ~30px mismatch between where
// the header text points and where the input visually sits, not a
// width/class bug (that part was already fixed). Mirroring the exact same
// flex structure in the header -- a same-width invisible spacer standing in
// for the diff-slot -- makes the header's own flexbox center the label over
// the SAME visual input position as the body, instead of over empty space
// the operator doesn't actually edit in. Reused by every editable grid's
// Or Qty header (Qty Check/Pending/Review/By Supplier); Assigned's Or Qty
// is a plain read-only number with no input/diff-slot, so it doesn't use
// this and isn't affected.
function OwOrQtyHeaderLabel({ label }) {
  return (
    <span className="ow-qty-header-cell">
      <span className="ow-qty-header-label">{label}</span>
      <span className="ow-qty-diff-slot" aria-hidden="true" />
    </span>
  );
}
// Body <td> className for a column -- deliberately reuses owHeaderClass's
// align/key logic (minus the icon-th sticky-header-only styling, which has
// no meaning on a body cell) so 'orqty' always carries the same
// ow-orqty-col marker in the body as it does in the header.
function owBodyCellClass(key, align) {
  const base = align === 'right' ? 'ow-num' : undefined;
  if (key === 'orqty') return `${base} ow-orqty-col`.trim();
  return base;
}
// One small filter control per filterable column, as a second header row
// under the labels -- the per-grid "filter at grid header" request. Reuses
// the SAME column-def objects (key/label/align) the headers themselves are
// built from, so a filter control is automatically present/absent/positioned
// in sync with whatever columns that grid actually shows.
function OwFilterRow({ cols, gridKind, values, onChange, wantedOptions }) {
  return (
    <tr className="ow-filter-row">
      {cols.map((c) => (
        <th key={c.key} className={owHeaderClass(c.key, c.align)}>
          {!OW_UNFILTERABLE_COLS.has(c.key) && (
            c.key === 'wanted' ? (
              <select
                className="ow-filter-select"
                value={values?.[c.key] || ''}
                onClick={(e) => e.stopPropagation()}
                onChange={(e) => onChange(gridKind, c.key, e.target.value)}
                aria-label={`Filter ${c.label}`}
              >
                <option value="">All</option>
                {(wantedOptions || []).map((w) => <option key={w} value={w}>{w}</option>)}
              </select>
            ) : c.key === 'offer' ? (
              <select
                className="ow-filter-select"
                value={values?.[c.key] || ''}
                onClick={(e) => e.stopPropagation()}
                onChange={(e) => onChange(gridKind, c.key, e.target.value)}
                aria-label="Filter offer products"
              >
                <option value="">All</option>
                {OW_OFFER_FILTER_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            ) : (
              <input
                type="text" className="ow-filter-input" placeholder="Filter…"
                value={values?.[c.key] || ''}
                onClick={(e) => e.stopPropagation()}
                onChange={(e) => onChange(gridKind, c.key, e.target.value)}
                aria-label={`Filter ${c.label}`}
              />
            )
          )}
        </th>
      ))}
    </tr>
  );
}

// EXACT-pixel colgroup + a trailing filler <col> (no width). With
// table-layout:fixed the fixed columns render at their literal px and the
// filler absorbs any leftover width — so slack never inflates a real column
// (spec §5-7: leave empty space / use a filler, never expand Product).
// fitWidth (the grid's visible width): on a smaller window, when the columns
// add up to more than that, shrink to fit instead of pushing the right-hand
// columns (LPD/LSD/Review) off-screen — the ellipsized Product column gives up
// width first (down to 140px), then every column scales down proportionally.

// resolveOwColumns/OwGridSettings/OwSupplierPicker/OwExportCard/OW_GEAR_PATH/
// OW_EXPORT_COLUMN_DEFS moved to ./OwSharedControls.jsx (NEXORA MEDIQ Phase 4
// structural refactor) -- shared by Order Workspace, Procurement (via
// PROCUREMENT_UI below) and the Label Exporter screen. No behavior changed.

// Order Workspace — VB-style ordering console ported into the desktop client
// (Purchase-Manager tool). Self-contained via the /api/legacy-order endpoints,
// keyed by store_name (independent of the desktop tenant/store GUID context).
// v1 covers the core workflow: store pick, Qty Review (Enter accept / Esc no-need
// / ↑↓ navigate) and Review All (inline qty edit), the workflow summary + Finalize,
// and the Previous-decisions strip. Supplier assignment + product intelligence are
// intentionally deferred (see web OrderWorkspacePage for the full feature set).

// Mirrors the legacy VB.NET "Select Process" combobox, trimmed to the five
// functions this client supports (owner-scoped: everything else -- Access DB,
// Compare Supplier/Previous Order, Supplier Invoice, Integrate Order and
// Purchase, Supplier Excel Mapping, UnifiedSupplierCode -- is out of scope
// here, not merely disabled). `supplierMode` picks which of the By Supplier
// screen's History/Live Stock queries a process lands on (Auto Pur UpDate =
// LoadDataForSupplier/purchase-history; Order Based Supplier Stock =
// LoadDataForSupplierStock/live-supplier-stock). "Supplier Order Details"
// is FetchSupplierOrderDetails in the VB.NET source -- status=1 rows already
// assigned to the picked supplier -- which is our `assigned` view, not
// `supplier`/history (those are different queries in the real source).
const OW_PROCESS_OPTIONS = [
  { key: 'qty_check', label: 'Qty Check', view: 'qty' },
  // Reviewed lines -> best-margin supplier over the last 5 supplies, else the
  // most frequent supplier (owner rule 2026-10-25; see bulkAssign.jsx).
  { key: 'bulk_assign', label: 'Bulk Assign · Best Margin', view: 'bulkassign' },
  // Pending Order = reviewed lines with Or Qty > 0; Or Qty 0 is a rejected
  // line, listed under Rejected (owner ruling 2026-10-25). Same loader.
  { key: 'pending_order', label: 'Pending Order', view: 'pending', pendingScope: 'order' },
  { key: 'rejected', label: 'Rejected', view: 'pending', pendingScope: 'rejected' },
  { key: 'auto_pur_update', label: 'Auto Pur UpDate', view: 'supplier', supplierMode: 'history' },
  { key: 'order_based_supplier_stock', label: 'Order Based Supplier Stock', view: 'supplier', supplierMode: 'stock' },
  { key: 'supplier_order_details', label: 'Supplier Order Details', view: 'assigned' },
];
// Qty Check limited to abnormal-sale products; listed under Qty Check in the
// Process dropdown only while the store has abnormal sales.
const OW_ABNORMAL_PROCESS_KEY = 'qty_check_abnormal';

export default function OrderWorkspace({ session, settings, hidden }) {
  void settings;
  const [stores, setStores] = useState([]);
  const [store, setStore] = useState(() => {
    if (DEV_STORE) return DEV_STORE;
    try { return localStorage.getItem('nexora.desktop.owStore') || ''; } catch { return ''; }
  });
  const [view, setView] = useState('qty'); // 'qty' | 'pending' | 'review' | 'supplier' | 'assigned'
  const [pendingScope, setPendingScope] = useState('order'); // pending view: 'order' (Or Qty > 0) | 'rejected' (Or Qty 0)
  const [qtyRows, setQtyRows] = useState([]);
  // Rows committed (Enter/Escape/blur) THIS session, kept visible but marked
  // reviewed instead of vanishing -- they drop off for real only on the next
  // actual reload (switching view/store/process), matching the grid staying
  // stable while you work down it instead of rows jumping out from under you.
  const [reviewedCodes, setReviewedCodes] = useState(() => new Set());
  // Original orderqty as first loaded, captured before any commit overwrites
  // row.orderqty -- lets the diff badge keep showing what actually changed
  // (e.g. ▼ -3) on a reviewed row instead of resetting to 0 once the commit
  // makes the row's live value equal its own new baseline.
  const [originalQty, setOriginalQty] = useState({});
  const [pendingRows, setPendingRows] = useState([]);
  const [rows, setRows] = useState([]);
  // Same baseline-capture idea as originalQty above, but for the Review All /
  // By Supplier grids (PascalCase ProductCode/OrderQty rows) so their OrderQty
  // edits can show the same +/- diff badge once committed.
  const [originalOrderQty, setOriginalOrderQty] = useState({});
  const [edits, setEdits] = useState({});
  const [savingCode, setSavingCode] = useState(null);
  const [resettingPending, setResettingPending] = useState(false);
  const [selectedCode, setSelectedCode] = useState(null);
  const [history, setHistory] = useState([]);
  const [workflow, setWorkflow] = useState(null);
  // Footer: order number/date + last GRN number/date for the current store's
  // latest order, read from OrderHeaderDetails (see repository.order_header_summary).
  // null = not loaded yet, 'error' = load failed -- kept distinct from "loaded
  // but store has no order yet" (an object with order_id: null) so the footer
  // can show a real unavailable state instead of a silently-empty one.
  const [orderHeader, setOrderHeader] = useState(null);
  const [orderHeaderError, setOrderHeaderError] = useState(false);
  const [search, setSearch] = useState('');
  // Mirrors VB.NET's cboProductType combo (All / Pharma / Non Pharma),
  // shown on Qty Check / Pending Order / Review All -- see GetQtyCheckQuery.
  const [productType, setProductType] = useState('All');
  const [wantedFilter, setWantedFilter] = useState('All');
  // Per-column header filters: { [view]: { [columnKey]: "typed text" } }. Kept
  // separate per grid (view) since each has its own column set and switching
  // grids shouldn't carry a filter typed into a column that doesn't exist
  // there. Plain "contains" match against that column's own rendered text.
  const [columnFilters, setColumnFilters] = useState({});
  // Filter row is OFF by default -- always-visible filter boxes ate a full
  // extra row of vertical space on every grid even when nobody was using
  // them. A toolbar toggle shows/hides it on demand instead.
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const qtyRefs = useRef([]);
  // Qty Check row's first CELL (whichever column that is -- columns are
  // user-reorderable here) -- the keyboard-focus target for a row clicked
  // somewhere other than its Or Qty box, so arrow keys navigate rows instead
  // of just scrolling the page (a <tr> with no handler at all did nothing).
  const qtyRowRefs = useRef([]);
  const reviewQtyRefs = useRef([]);
  // Review All row's first cell -- same row-click-didn't-land-on-the-input
  // gap as Qty Check above.
  const reviewRowRefs = useRef([]);
  const supplierQtyRefs = useRef([]);
  // Row (<tr>) elements for the By Supplier grid -- the keyboard-focus target
  // for rows whose qty box is disabled (assigned rows), so arrow navigation
  // works no matter which part of the row has focus.
  const supplierRowRefs = useRef([]);
  // Supplier Order Details (Assigned) grid is read-only (no qty inputs), so its
  // keyboard navigation unit is the row itself.
  const assignedRowRefs = useRef([]);
  const pendingQtyRefs = useRef([]);
  // Pending Order row's first cell -- same row-click-didn't-land-on-the-input
  // gap as Qty Check/Review All.
  const pendingRowRefs = useRef([]);
  // Set right before a key handler (ArrowUp/Down/Escape/Backspace) moves
  // focus to another row's input programmatically. The By Supplier grid's
  // qty box also has onBlur={saveOrderQty} for genuine "click away" edits --
  // without this guard, every programmatic focus() triggers that SAME
  // blur-save as a duplicate, racing API call right alongside
  // commitSupplierQty's own save of the identical value. That race is what
  // was breaking keyboard-driven focus movement (the blur-save's own
  // re-render/side-effects could land after and invalidate the just-set
  // focus, making it look like Escape/arrows "kicked focus out of the grid"
  // and only mouse clicks worked).
  const skipBlurSaveRef = useRef(false);

  // Supplier assignment (By Supplier / Assigned views).
  const [supplierMode, setSupplierMode] = useState('history'); // 'history' | 'stock'
  // "Load all products": By Supplier grid shows every open orderable product,
  // not just the picked supplier's history/stock match -- lets the operator
  // assign a product the per-supplier match missed. Forces the history-shape
  // (non-stock) layout since the per-supplier stock columns don't exist for an
  // unmatched product.
  const [loadAll, setLoadAll] = useState(false);
  const [suppliers, setSuppliers] = useState([]);
  const [supplier, setSupplier] = useState(null);
  const [assigned, setAssigned] = useState([]);
  const [statusOverride, setStatusOverride] = useState({});
  // Local-only "remove from view" (VB.NET's Delete key -> dgvMain.Rows.Remove):
  // hides a row from THIS working session without touching the database, so
  // it's simply skipped for the current supplier and stays available (still
  // status=0) to assign to a different supplier later. Keyed by ProductCode;
  // cleared whenever the supplier/store/view changes (new working set).
  const [removedCodes, setRemovedCodes] = useState(() => new Set());
  // "Not reviewed yet" badge for the By Supplier (history) grid: a row whose
  // Qtycheck came back 0 from the server shows a badge until the operator
  // edits its OrderQty right here, at which point it's treated as reviewed
  // for the rest of this working set -- same reset points as removedCodes.
  const [qtyCheckedHere, setQtyCheckedHere] = useState(() => new Set());
  const [assigningCode, setAssigningCode] = useState(null);
  const [banner, setBanner] = useState('');
  // Files the last export wrote + who they're for, for "Send on WhatsApp".
  const [lastExport, setLastExport] = useState(null);
  const [waSendOpen, setWaSendOpen] = useState(false);
  // Export + split.
  const [exportOpen, setExportOpen] = useState(false);
  const [splitCount, setSplitCount] = useState(0);
  const [exporting, setExporting] = useState(false);
  const [removingUnavailable, setRemovingUnavailable] = useState(false);
  const exportBtnRef = useRef(null);
  // Bumped after a successful export to re-fetch the grid, since export bulk-
  // assigns every exported row to the supplier server-side (status changes).
  const [reloadTick, setReloadTick] = useState(0);
  // Export destination/format/columns — loaded once from disk (or
  // localStorage on the web build), then kept in sync on every change so a
  // changed default path survives an app restart. See owDefaultExportSettings.
  const [exportSettings, setExportSettings] = useState(owDefaultExportSettings);
  useEffect(() => {
    readOwExportSettings().then((loaded) => {
      // Persist the one-time migrations immediately -- otherwise they
      // silently "fix themselves" every load without ever updating the
      // saved file, which looks fixed in THIS session but reverts on the
      // next app restart (the saved old value would still win every
      // subsequent {...default, ...saved} merge).
      if (loaded._migratedSupplierWiseOff || loaded._migratedFileFormatXls) writeOwExportSettings(loaded);
      setExportSettings(loaded);
    });
  }, []);
  const updateExportSettings = (patch) => setExportSettings((cur) => {
    const next = { ...cur, ...patch };
    writeOwExportSettings(next);
    return next;
  });

  // Per-grid column settings (show/hide, order, width), persisted per grid id.
  // v2: bumped so stale column widths (which pinned a narrow Product Name) are
  // discarded and the new wider defaults take effect.
  const [owColCfg, setOwColCfg] = useState(() => {
    try { return JSON.parse(localStorage.getItem('nexora.desktop.owGridColumns.v2') || '{}') || {}; } catch { return {}; }
  });
  const [settingsFor, setSettingsFor] = useState(null); // 'qty' | 'review' | null
  const settingsBtnRef = useRef(null);
  useEffect(() => {
    try { localStorage.setItem('nexora.desktop.owGridColumns.v2', JSON.stringify(owColCfg)); } catch { /* best effort */ }
  }, [owColCfg]);
  const cfgToggle = (id, key) => setOwColCfg((c) => { const g = { ...(c[id] || {}) }; const hidden = { ...(g.hidden || {}) }; hidden[key] = !hidden[key]; return { ...c, [id]: { ...g, hidden } }; });
  const cfgMove = (id, base, key, dir) => setOwColCfg((c) => { const order = orderOwKeys(base, c[id]); const i = order.indexOf(key); const j = i + dir; if (i < 0 || j < 0 || j >= order.length) return c; const n = [...order]; [n[i], n[j]] = [n[j], n[i]]; return { ...c, [id]: { ...(c[id] || {}), order: n } }; });
  const cfgWidth = (id, key, w) => setOwColCfg((c) => { const g = { ...(c[id] || {}) }; const widths = { ...(g.widths || {}) }; if (w === '' || w == null) delete widths[key]; else widths[key] = Number(w); return { ...c, [id]: { ...g, widths } }; });
  const cfgReset = (id) => setOwColCfg((c) => { const n = { ...c }; delete n[id]; return n; });
  const [owLayout, setOwLayout] = useState(() => {
    try { return owNormalizeLayout(JSON.parse(localStorage.getItem('nexora.desktop.owLayout') || '{}')); }
    catch { return owNormalizeLayout(null); }
  });
  // Purchase / sales row clicked in a detail panel -> whole invoice / bill card.
  const [owRecord, setOwRecord] = useState(null);
  const [lineCollapsed, setLineCollapsed] = useState(false);
  const [infoCode, setInfoCode] = useState(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [linePrices, setLinePrices] = useState(null);
  useEffect(() => { setLinePrices(null); }, [selectedCode, store]);
  useEffect(() => {
    try { localStorage.setItem('nexora.desktop.owLayout', JSON.stringify(owLayout)); } catch { /* best effort */ }
  }, [owLayout]);

  useEffect(() => {
    api.legacyStores(session)
      .then((list) => {
        const arr = asArray(list);
        setStores(arr);
        // Keep the current/remembered store if it's still valid; else first store.
        setStore((cur) => (cur && arr.some((s) => s.store_name === cur)) ? cur : (arr[0]?.store_name || ''));
      })
      .catch((e) => setError(e.message));
  }, [session]);

  // Remember the selected store across reloads/relaunches (localStorage).
  useEffect(() => {
    if (store) { try { localStorage.setItem('nexora.desktop.owStore', store); } catch { /* best effort */ } }
  }, [store]);

  const loadWorkflow = useCallback(() => {
    if (!store) return;
    api.legacyOrderWorkflow(store, session).then(setWorkflow).catch((e) => setError(e.message));
  }, [store, session]);
  // Clear the previous store's counts the instant the store changes -- left
  // alone, a failed/slow workflow fetch for the new store left the OLD
  // store's "Pending N · Assigned N · Open N" chip on screen, now visually
  // attributed to the newly selected store (the same stale-cross-store
  // problem the grid-clearing fix above addresses, for this one piece of
  // state it missed).
  useEffect(() => { setWorkflow(null) }, [store]);
  useEffect(() => { loadWorkflow(); }, [loadWorkflow]);

  // Footer order/GRN metadata -- same store-keyed load/clear pattern as the
  // workflow chip above: clear instantly on store change so the previous
  // store's order number never lingers under the new store name, then
  // refetch. Also re-run on reloadTick (export/assign reassigns rows, which
  // moves the workflow's UpdatedAt) so the footer and the fingerprint below
  // stay representative of what's actually on screen.
  useEffect(() => { setOrderHeader(null); setOrderHeaderError(false); }, [store]);
  useEffect(() => {
    if (!store) return undefined;
    let cancelled = false;
    api.legacyOrderHeader(store, session)
      .then((r) => { if (!cancelled) { setOrderHeader(r); setOrderHeaderError(false); } })
      .catch(() => { if (!cancelled) setOrderHeaderError(true); });
    return () => { cancelled = true; };
  }, [store, session, reloadTick]);

  // Freshness check on RETURN to this screen (hidden: true -> false), not on
  // every header poll while the user is actively working here -- their own
  // qty/assign edits also move the fingerprint (order_id, updated_at), and
  // reacting to that would wrongly tell them "order data changed" about a
  // change they just made themselves. Only a transition back from another
  // screen is "time may have passed elsewhere," so only check then: compare
  // the fingerprint captured when this screen was last left against the
  // freshly-polled one, and if either half moved -- a regeneration (new
  // order_id) or a line-level edit from elsewhere (same order_id, later
  // updated_at) -- force the same reload+reselect path a manual store
  // switch already takes, rather than leaving stale rows on screen.
  const wasHidden = useRef(hidden);
  const leftFingerprint = useRef(null);
  useEffect(() => {
    if (hidden) {
      if (orderHeader && orderHeader.order_id != null) {
        leftFingerprint.current = `${orderHeader.order_id}|${orderHeader.updated_at ?? ''}`;
      }
    } else if (wasHidden.current && store) {
      api.legacyOrderHeader(store, session).then((fresh) => {
        if (fresh.order_id == null) return;
        const freshFp = `${fresh.order_id}|${fresh.updated_at ?? ''}`;
        if (leftFingerprint.current !== null && leftFingerprint.current !== freshFp) {
          setBanner('Order data changed. The latest data has been loaded, and selection was reset to the first product.');
          setReloadTick((t) => t + 1);
        }
        setOrderHeader(fresh);
      }).catch(() => {});
    }
    wasHidden.current = hidden;
  }, [hidden, store, session]);

  // Supplier combo list: fetched once per store, not re-fetched on every
  // switch into/out of By Supplier or Assigned -- the list doesn't change
  // mid-session, and over a slow/high-latency link (remote stores on the
  // internet) a redundant few-hundred-row re-fetch on every tab switch was
  // real, visible lag. Loads lazily the first time either view needs it.
  const suppliersLoadedForStore = useRef(null);
  useEffect(() => { suppliersLoadedForStore.current = null; setSuppliers([]); }, [store]);
  useEffect(() => {
    if (!store || (view !== 'supplier' && view !== 'assigned')) return;
    if (suppliersLoadedForStore.current === store) return;
    suppliersLoadedForStore.current = store;
    api.legacySuppliers(store, '', session)
      .then((r) => setSuppliers(asArray(r)))
      .catch((e) => { suppliersLoadedForStore.current = null; setError(e.message); });
  }, [store, view, session]);

  useEffect(() => {
    if (!store) return undefined;
    let cancelled = false;
    setLoading(true); setError(''); setEdits({}); setSelectedCode(null); setInfoCode(null); setLinePrices(null); setStatusOverride({}); setRemovedCodes(new Set()); setQtyCheckedHere(new Set());
    // Clear the PREVIOUS view/store's grid rows synchronously, in the same
    // tick as the state change that triggered this effect -- otherwise the
    // old store/process/supplier's rows stay fully rendered (and editable)
    // on screen for the entire round trip, which on a slow/remote link reads
    // as "the grid didn't react yet, did my click even register" and risks
    // an operator editing/assigning against the wrong store's stale rows for
    // a moment. Only clear the array this `view` is about to repopulate --
    // the other grids' arrays are left alone since their own view-branch
    // will clear them when the operator actually switches there (avoids
    // redundant re-renders of grids that aren't even visible right now).
    if (view === 'qty') setQtyRows([]);
    else if (view === 'pending') setPendingRows([]);
    else if (view === 'review' || view === 'supplier' || view === 'bulkassign') setRows([]);
    else setAssigned([]);
    const done = () => { if (!cancelled) setLoading(false); };
    // Selects row 0 once the grid's data lands, same as VB.NET's
    // FocusOrderQtyCell -- the grid opens with a row already current instead
    // of nothing selected until the user clicks in.
    if (view === 'qty') {
      setReviewedCodes(new Set());
      api.legacyQtyCheckRows(store, session)
        .then((r) => {
          if (cancelled) return;
          const list = asArray(r);
          setQtyRows(list);
          setOriginalQty(Object.fromEntries(list.map((row) => [row.productcode, row.orderqty])));
          // Highlight row 0 as current (matches VB.NET's grid opening on a
          // current row) WITHOUT stealing keyboard focus into its qty input --
          // forcing focus there let an unrelated click elsewhere on the page
          // blur it mid-click and auto-commit that row as "reviewed" before
          // the user had touched anything.
          if (list.length) setSelectedCode(list[0].productcode);
        })
        .catch((e) => { if (!cancelled) setError(e.message); })
        .finally(done);
    } else if (view === 'pending') {
      api.legacyPendingOrderRows(store, session)
        .then((r) => {
          if (cancelled) return;
          const list = asArray(r);
          setPendingRows(list);
          if (list.length) setSelectedCode(list[0].productcode);
        })
        .catch((e) => { if (!cancelled) setError(e.message); })
        .finally(done);
    } else if (view === 'review') {
      api.legacyOrders(store, session)
        .then((r) => {
          if (cancelled) return;
          const list = asArray(r);
          setRows(list);
          setOriginalOrderQty(Object.fromEntries(list.map((row) => [row.ProductCode, row.OrderQty])));
          if (list.length) setSelectedCode(list[0].ProductCode);
        })
        .catch((e) => { if (!cancelled) setError(e.message); })
        .finally(done);
    } else if (view === 'supplier') {
      // Load all products: every open orderable row, no supplier needed to
      // view (a supplier is still required to assign/export). Otherwise the
      // per-supplier history/stock match -- which needs a supplier picked.
      if (!loadAll && !supplier) { setRows([]); done(); return () => { cancelled = true; }; }
      const req = loadAll
        ? api.legacyAllOpenOrders(store, session)
        : api.legacyOrdersBySupplier(store, supplier.supplier_code, supplierMode, session);
      req
        .then((r) => {
          if (cancelled) return;
          const list = asArray(r);
          setRows(list);
          setOriginalOrderQty(Object.fromEntries(list.map((row) => [row.ProductCode, row.OrderQty])));
          if (list.length) setSelectedCode(list[0].ProductCode);
        })
        .catch((e) => { if (!cancelled) setError(e.message); })
        .finally(done);
    } else if (view === 'bulkassign') {
      done(); // OwBulkAssign loads its own proposals.
    } else { // assigned
      if (!supplier) { setAssigned([]); done(); return () => { cancelled = true; }; }
      api.legacyAssignedOrders(store, supplier.supplier_code, session)
        .then((r) => {
          if (cancelled) return;
          const list = asArray(r);
          setAssigned(list);
          if (list.length) setSelectedCode(list[0].ProductCode);
        })
        .catch((e) => { if (!cancelled) setError(e.message); })
        .finally(done);
    }
    return () => { cancelled = true; };
  }, [store, view, session, supplier, supplierMode, loadAll, reloadTick]);

  useEffect(() => {
    if (!store || selectedCode == null) { setHistory([]); setHistoryLoading(false); return undefined; }
    let cancelled = false;
    setHistoryLoading(true);
    api.legacyOrderHistory(store, selectedCode, session)
      .then((r) => { if (!cancelled) setHistory(asArray(r)); })
      .catch(() => { if (!cancelled) setHistory([]); })
      .finally(() => { if (!cancelled) setHistoryLoading(false); });
    return () => { cancelled = true; };
  }, [store, selectedCode, session]);

  // Default keyboard focus onto row 0's OR QTY box once a grid finishes
  // loading, matching VB.NET's FocusOrderQtyCell -- the operator can start
  // typing/arrowing immediately instead of having to click in first. Safe to
  // steal focus here (unlike the selection-only row-0 highlight set above)
  // because none of the three grids commit/mark-reviewed on blur alone --
  // only an explicit ArrowUp/ArrowDown does that for the Qty Check grid, and
  // the Supplier grid's onBlur only re-saves the already-displayed value.
  useEffect(() => {
    if (loading) return;
    const refs = view === 'qty' ? qtyRefs : view === 'supplier' ? supplierQtyRefs : view === 'assigned' ? assignedRowRefs : reviewQtyRefs;
    const frame = requestAnimationFrame(() => {
      if (document.activeElement === document.body || !document.activeElement || document.activeElement.tagName === 'BODY') {
        refs.current[0]?.focus();
      }
    });
    return () => cancelAnimationFrame(frame);
  }, [loading, view]);

  const finalized = workflow?.status === 'FINALIZED';
  const term = search.trim().toLowerCase();
  // Abnormal bill sales of this store's open order (rulebook PRR-SALE-
  // ABNORMAL / PRR-SALE-WARNING). On the first load of a store with abnormal
  // sales the grids open filtered to those products for PM review.
  const abnormal = useAbnormalSales({
    enabled: Boolean(store),
    key: `${store}|${reloadTick}`,
    load: () => api.legacyAbnormalSales(store, session),
    save: (productCode, bill, value) => api.legacySetDontConsider(store, {
      product_code: String(productCode), bill_no: bill.bill_no, bill_date: bill.bill_date, dont_consider: value,
    }, session),
  });
  const [abnormalOnly, setAbnormalOnly] = useState(false);
  const abnormalOpenedFor = useRef('');
  useEffect(() => { setAbnormalOnly(false); }, [store]);
  // The abnormal list is a Qty Check process option ("Qty Check · Abnormal
  // sales" in the Process dropdown), so any other process clears it.
  useEffect(() => { if (view !== 'qty') setAbnormalOnly(false); }, [view]);
  useEffect(() => {
    if (!store || abnormal.loading || abnormalOpenedFor.current === store) return;
    if (abnormal.items.length || abnormal.error) abnormalOpenedFor.current = store;
    if (abnormal.abnormalCount > 0 && view === 'qty') setAbnormalOnly(true);
  }, [store, abnormal.loading, abnormal.items.length, abnormal.abnormalCount, abnormal.error, view]);
  const match = (name, code) => (!abnormalOnly || Boolean(abnormal.byCode[String(code)]))
    && (!term || String(name || '').toLowerCase().includes(term) || String(code).includes(term));
  const matchWanted = (wanted) => wantedFilter === 'All' || (wanted ?? '—') === wantedFilter;

  // Per-column header filters (request: "allow user to filter view" directly
  // from each grid's header, not just the toolbar's Product Type/Wanted
  // dropdowns). One small text box per column, plain case-insensitive
  // "contains" against that column's own displayed value. ownFieldText maps a
  // (grid, columnKey) pair to the row's raw field -- each grid shape differs
  // (lowercase vs PascalCase, different field names), so this is the one
  // place that knowledge lives rather than duplicating it per filter box.
  function ownFieldText(gridKind, key, row) {
    switch (gridKind === 'qty' || gridKind === 'pending' ? 'lc' : 'pc') {
      case 'lc': switch (key) {
        case 'name': return row.productname;
        case 'offer': return row.IsOffer ? 'Yes' : '';
        case 'orqty': return row.orderqty;
        case 'stock': return row.totalstock;
        case 'pack': return row.saleunit;
        case 'desc': return row.unitdescription;
        case 'slsqty': return row.slsqty;
        case 'mrp': return row.mrp;
        case 'lrdate': return row.lastreceiveddate;
        case 'lsdate': return row.lastsaledate;
        case 'maxqty': return row.maxsaleqty;
        case 'wanted': return row.wantedtype;
        default: return null;
      }
      default: switch (key) {
        case 'name': return row.ProductName;
        case 'offer': return row.IsOffer ? 'Yes' : '';
        case 'orqty': return row.OrderQty;
        case 'stock': return row.TotalStock;
        case 'pack': return row.SaleUnit;
        case 'desc': return row.UnitDescription;
        case 'slsqty': case 'sls': return row.SLSQty;
        case 'mrp': return row.MRP;
        case 'sstock': return row.S_Stock;
        case 'disc': return row.Discount;
        case 'minqty': return row.MinQty;
        case 'rack': return row.Rack;
        case 'wanted': return row.WantedType;
        case 'supplier': return row.OrSupplier;
        case 'remarks': return row.Remarks;
        default: return null;
      }
    }
  }
  function matchColumnFilters(gridKind, row) {
    const filters = columnFilters[gridKind];
    if (!filters) return true;
    return Object.entries(filters).every(([key, raw]) => {
      const needle = (raw || '').trim().toLowerCase();
      if (!needle) return true;
      // 'offer' is a real boolean (IsOffer), not text -- ownFieldText returns
      // '' for a non-offer row, which a plain .includes(needle) can never
      // match against "no" (an empty string never "contains" anything), so
      // this needs its own yes/no check instead of the generic text-contains
      // every other column uses.
      if (key === 'offer') return needle === 'yes' ? Boolean(row.IsOffer) : !row.IsOffer;
      const value = ownFieldText(gridKind, key, row);
      return String(value ?? '').toLowerCase().includes(needle);
    });
  }
  const setColFilter = (gridKind, key, value) => {
    setColumnFilters((cur) => ({ ...cur, [gridKind]: { ...(cur[gridKind] || {}), [key]: value } }));
  };

  const filteredQty = useMemo(() => qtyRows.filter((r) => (
    match(r.productname, r.productcode) && (productType === 'All' || r.producttypename === productType) && matchWanted(r.wantedtype) && matchColumnFilters('qty', r)
  )), [qtyRows, term, abnormalOnly, abnormal.byCode, productType, wantedFilter, columnFilters.qty]);
  const filteredRows = useMemo(() => rows.filter((r) => (
    !removedCodes.has(r.ProductCode)
    && match(r.ProductName, r.ProductCode) && (productType === 'All' || r.ProductTypeName === productType) && matchWanted(r.WantedType)
    && matchColumnFilters(view === 'supplier' ? 'supplier' : 'review', r)
  )), [rows, term, abnormalOnly, abnormal.byCode, productType, removedCodes, wantedFilter, view, columnFilters.supplier, columnFilters.review]);
  // Filtered client-side like every other grid -- pendingRows is fetched
  // once per store/view (Pharma + Non Pharma, matching VB.NET's "All") and
  // never re-fetched just because the product-type filter changed.
  const filteredPending = useMemo(() => pendingRows.filter((r) => (
    (pendingScope === 'rejected' ? !(Number(r.orderqty) > 0) : Number(r.orderqty) > 0)
    && match(r.productname, r.productcode) && (productType === 'All' || r.producttypename === productType) && matchWanted(r.wantedtype) && matchColumnFilters('pending', r)
  )), [pendingRows, pendingScope, term, abnormalOnly, abnormal.byCode, productType, wantedFilter, columnFilters.pending]);
  // Distinct Wanted values actually present in whichever grid is active --
  // a dropdown of real values, not a hardcoded guess at the legacy DB's
  // fixed-string set, so it stays correct if that set ever changes.
  const wantedOptions = useMemo(() => {
    const source = view === 'qty' ? qtyRows : view === 'pending' ? pendingRows : rows;
    const key = view === 'qty' || view === 'pending' ? 'wantedtype' : 'WantedType';
    const values = new Set();
    source.forEach((r) => values.add(r[key] ?? '—'));
    return Array.from(values).sort();
  }, [view, qtyRows, pendingRows, rows]);
  useEffect(() => {
    if (wantedFilter !== 'All' && !wantedOptions.includes(wantedFilter)) setWantedFilter('All');
  }, [wantedOptions, wantedFilter]);

  // After removing a row, filteredRows shrinks by one and every later row
  // shifts up — so the row that was at `index + 1` is now AT `index`, and
  // refocusing that same index (not index+1) lands on what the operator
  // sees as "the next row" rather than jumping back to the top of the grid.
  // Deferred a frame so the ref array has re-rendered against the new,
  // shorter filteredRows before we read supplierQtyRefs.current[index].
  // Delete is VIEW-ONLY -- removes the row from this grid's local list, no
  // API call, no DB write at all. It does NOT zero the qty or touch
  // qtycheck; the row stays exactly as it was in the database and will
  // reappear next time this grid reloads. Backspace is the "Don't Want to
  // Order" shortcut that actually mutates (zero qty + qtycheck=1) -- see
  // onKeyDown below.
  const removeRow = (productCode, index) => {
    setRemovedCodes((cur) => new Set(cur).add(productCode));
    if (index != null) {
      supplierRowVirtualizer.scrollToIndex(index, { align: 'auto' });
      requestAnimationFrame(() => owFocusGridRow(supplierQtyRefs, supplierRowRefs, index));
    }
  };

  const resetPending = () => {
    if (!store) return;
    setResettingPending(true);
    api.legacyResetPendingQtyCheck(store, session)
      .then(({ assigned_marked, remaining_reset }) => {
        setBanner(`Reset pending: ${assigned_marked} assigned line(s) marked reviewed, ${remaining_reset} remaining line(s) reset to original qty.`);
        if (view === 'qty') setReloadTick((t) => t + 1);
      })
      .catch((e) => setError(e.message))
      .finally(() => setResettingPending(false));
  };

  // Persist the quantity and mark the row reviewed (qtycheck=1) -- only
  // called from ArrowUp/ArrowDown navigation (see onQtyKey below). The row
  // stays visible (marked reviewed) rather than vanishing mid-session; it
  // drops off for real only on the next actual reload (switching
  // view/store/process), so the grid doesn't jump around under you while
  // you're still working down it. Factory so Pending Order can reuse the
  // exact same commit behavior against its own row-list/ref-array.
  const makeCommitQty = (rowsSetter, refs) => (productCode, value, focusIndex) => {
    if (!store) return;
    // Move focus/selection to the next row IMMEDIATELY, not after the
    // network round-trip resolves -- the save happens in the background.
    // Waiting on the API call before moving focus meant any slowness (or a
    // silently-failed request) on a remote store's connection stalled
    // keyboard navigation entirely, which read as "up/down stopped working."
    requestAnimationFrame(() => refs.current[focusIndex]?.focus());
    setSavingCode(productCode);
    api.legacyUpdateQtyCheck(store, productCode, value, session)
      .then(() => {
        setReviewedCodes((cur) => new Set(cur).add(productCode));
        // Patch the committed value into the row list itself -- the displayed
        // value falls back to row.orderqty once the edit is cleared below,
        // so without this the field snaps back to the pre-edit quantity even
        // though the database write succeeded. Freeze orgorderqty to its
        // PRE-commit value at the same time: if it was ever null/undefined,
        // leaving it unset would make the diff arrow's `orgorderqty ??
        // orderqty` fallback collapse to the just-committed value itself
        // (orderqty) once that's overwritten below -- comparing a number
        // against itself always reads as "no change," which is exactly what
        // made the diff arrow vanish/show a flat dash right after commit.
        rowsSetter((cur) => cur.map((r) => (
          r.productcode === productCode ? { ...r, orgorderqty: r.orgorderqty ?? r.orderqty, orderqty: value } : r
        )));
        setEdits((cur) => { const n = { ...cur }; delete n[productCode]; return n; });
      })
      .catch((e) => setError(e.message))
      .finally(() => { setSavingCode(null); loadWorkflow(); });
  };
  const commitQty = makeCommitQty(setQtyRows, qtyRefs);

  // ArrowUp/ArrowDown mark a row reviewed on the way out. Clicking into the
  // cell, Tab, or clicking away must NOT commit/mark qtycheck. Enter saves an
  // edit in place (so a typed value isn't lost) without marking reviewed or
  // moving focus. Escape is the explicit "Don't Want to Order" shortcut --
  // zeroes the qty AND marks it reviewed in one step. Shared by the Qty Check
  // grid and Pending Order (which now allows the same inline edit, since a
  // pending row can still have its quantity corrected without bouncing back
  // through Qty Check) -- parameterized by which row-list/length/commit
  // function to act on so the two grids don't duplicate this logic.
  const makeOnQtyKey = (rowsSetter, filteredLength, commit) => (e, row, index) => {
    if (e.key === '+' || e.key === '-') {
      // Quick keyboard +1/-1, same effect as clicking the stepper arrow,
      // without leaving the row or committing/marking reviewed.
      e.preventDefault();
      const current = owWholeQty(edits[row.productcode] ?? row.orderqty);
      const next = e.key === '+' ? current + 1 : Math.max(0, current - 1);
      setEdits((cur) => ({ ...cur, [row.productcode]: next }));
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      const value = Number(edits[row.productcode] ?? row.orderqty);
      commit(row.productcode, value, Math.min(index + 1, filteredLength - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      const value = Number(edits[row.productcode] ?? row.orderqty);
      commit(row.productcode, value, Math.max(index - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      // Save the value without marking reviewed or moving focus.
      const value = Number(edits[row.productcode] ?? row.orderqty);
      if (!store) return;
      setSavingCode(row.productcode);
      api.legacyUpdateQtyCheck(store, row.productcode, value, session)
        .then(() => {
          rowsSetter((cur) => cur.map((r) => (
            r.productcode === row.productcode ? { ...r, orgorderqty: r.orgorderqty ?? r.orderqty, orderqty: value } : r
          )));
          setEdits((cur) => { const n = { ...cur }; delete n[row.productcode]; return n; });
        })
        .catch((err) => setError(err.message))
        .finally(() => setSavingCode(null));
    } else if (e.key === 'Escape' || (e.key === 'Backspace' && owIsClearKeypress(e))) {
      e.preventDefault();
      // "Don't Want to Order" -- zero the qty, mark reviewed, and advance to
      // the next row, same as ArrowDown (just with the value forced to 0
      // instead of whatever's currently typed). Backspace only triggers this
      // when there's nothing left to delete (field already empty, or the
      // whole value is selected) so normal digit-by-digit editing with
      // Backspace still works everywhere else; Delete (a separate key, see
      // removeRow) stays view-only and never calls this.
      commit(row.productcode, 0, Math.min(index + 1, filteredLength - 1));
    }
  };
  const onQtyKey = makeOnQtyKey(setQtyRows, filteredQty.length, commitQty);
  const commitPendingQty = makeCommitQty(setPendingRows, pendingQtyRefs);
  const onPendingQtyKey = makeOnQtyKey(setPendingRows, filteredPending.length, commitPendingQty);

  // ArrowUp/ArrowDown commits + marks reviewed (Qtycheck=1) in one step, same
  // as the dedicated Qty Check grid's commitQty -- lets History/Auto Pur
  // UpDate and Live Stock review products inline instead of requiring a
  // separate trip through the Qty Check grid first.
  const commitSupplierQty = (row, value, focusIndex) => {
    if (!store) return;
    // See makeCommitQty -- focus moves immediately, not after the network
    // round-trip, so navigation never stalls on a slow/failed save. Guard
    // flag first so the blur this focus-move causes doesn't also fire
    // saveOrderQty as a duplicate/racing save (see skipBlurSaveRef above).
    skipBlurSaveRef.current = true;
    // scrollToIndex first -- with the By Supplier grid virtualized, a ref
    // outside the current virtual window is null until scrolled into view
    // (see assignedRowVirtualizer.scrollToIndex comment below).
    supplierRowVirtualizer.scrollToIndex(focusIndex, { align: 'auto' });
    requestAnimationFrame(() => {
      owFocusGridRow(supplierQtyRefs, supplierRowRefs, focusIndex);
      skipBlurSaveRef.current = false;
    });
    setSavingCode(row.ProductCode);
    api.legacyUpdateQtyCheck(store, row.ProductCode, value, session)
      .then(() => {
        // Freeze OrgOrderQty to its pre-commit value if it was ever null --
        // same fallback-collapse fix as makeCommitQty.
        setRows((cur) => cur.map((r) => (
          r.ProductCode === row.ProductCode ? { ...r, OrgOrderQty: r.OrgOrderQty ?? r.OrderQty, OrderQty: value, Qtycheck: 1 } : r
        )));
        setQtyCheckedHere((cur) => new Set(cur).add(row.ProductCode));
        setEdits((cur) => { const n = { ...cur }; delete n[row.ProductCode]; return n; });
      })
      .catch((e) => setError(e.message))
      .finally(() => setSavingCode(null));
  };

  const saveOrderQty = (row, value) => {
    if (!store || value === row.OrderQty) return;
    setSavingCode(row.ProductCode);
    api.legacyUpdateOrderQty(store, row.ProductCode, value, session)
      .then(() => {
        setRows((cur) => cur.map((r) => (
          r.ProductCode === row.ProductCode ? { ...r, OrgOrderQty: r.OrgOrderQty ?? r.OrderQty, OrderQty: value } : r
        )));
      })
      .catch((e) => setError(e.message))
      .finally(() => { setSavingCode(null); loadWorkflow(); });
  };

  const finalize = (reopen) => {
    if (!store) return;
    const note = window.prompt(reopen ? 'Why is this order being reopened?' : 'Optional finalization note:');
    if (note === null) return;
    const call = reopen ? api.legacyReopenOrder(store, note, session) : api.legacyFinalizeOrder(store, note, session);
    call.then(setWorkflow).catch((e) => setError(e.message));
  };

  // Supplier assignment (By Supplier view). Assign/unassign the selected supplier
  // to a row; the toggle returns the new status so the row flips green in place.
  const statusOf = (row) => statusOverride[row.ProductCode] ?? row.Status;
  const filteredAssigned = useMemo(() => assigned.filter((r) => (
    match(r.ProductName, r.ProductCode) && (productType === 'All' || r.ProductTypeName === productType) && matchColumnFilters('assigned', r)
  )), [assigned, term, abnormalOnly, abnormal.byCode, productType, columnFilters.assigned]);

  // By Supplier "Load all products" can be 1000s of open rows rendered as a
  // plain <table>.map() -- same freeze-on-any-unrelated-state-change problem
  // as the Label Exporter grid (see its rowVirtualizer comment), just
  // triggered by the loadAll toggle instead of a 3000+-product letter. Only
  // mount rows actually on screen. Fixed 30px matches .ow-fixed/.ow-cfg
  // tbody td's rendered height closely enough that overscan absorbs any
  // drift; both grids share the same .ow-grid scroll container (only one
  // table renders at a time) so one ref/one virtualizer each is enough.
  const owGridScrollRef = useRef(null);
  const supplierRowVirtualizer = useVirtualizer({
    count: filteredRows.length,
    getScrollElement: () => owGridScrollRef.current,
    estimateSize: () => 30,
    overscan: 12
  });
  const assignedRowVirtualizer = useVirtualizer({
    count: filteredAssigned.length,
    getScrollElement: () => owGridScrollRef.current,
    estimateSize: () => 30,
    overscan: 12
  });
  // Ordered product codes of whichever grid is on screen -- lets the detail
  // sidebar prefetch the next few upcoming rows' Purchase/Sales/Trend so
  // row-to-row navigation lands on already-loaded data instead of waiting on
  // three network round-trips each time.
  const owVisibleCodes = useMemo(() => {
    if (view === 'qty') return filteredQty.map((r) => r.productcode);
    if (view === 'pending') return filteredPending.map((r) => r.productcode);
    if (view === 'assigned') return filteredAssigned.map((r) => r.ProductCode);
    return filteredRows.map((r) => r.ProductCode); // review + supplier
  }, [view, filteredQty, filteredPending, filteredRows, filteredAssigned]);
  const canAssign = view === 'supplier' && Boolean(supplier);
  // Load-all forces the history-shape (non-stock) layout: the per-supplier
  // SupplierStock columns (S.Stock/Disc/MinQty/Rack) don't exist for a product
  // that isn't matched to the picked supplier.
  const isStockMode = view === 'supplier' && supplierMode === 'stock' && !loadAll;
  const supplierColsBase = owSupplierColumns(isStockMode);
  const supplierCols = resolveOwColumns(supplierColsBase, owColCfg.supplier);

  const toggleAssign = (row) => {
    if (!store || !supplier) return;
    setAssigningCode(row.ProductCode); setBanner('');
    const value = edits[row.ProductCode];
    const saveFirst = (value != null && value !== row.OrderQty)
      ? api.legacyUpdateOrderQty(store, row.ProductCode, value, session)
        .then(() => setRows((cur) => cur.map((r) => (r.ProductCode === row.ProductCode ? { ...r, OrderQty: value } : r))))
      : Promise.resolve();
    saveFirst
      .then(() => api.legacyAssignSupplier(store, row.ProductCode, supplier.supplier_code, supplier.supplier_name, session))
      .then((result) => {
        setStatusOverride((cur) => ({ ...cur, [row.ProductCode]: result.status }));
        setBanner(result.status === 1
          ? `Assigned ${row.ProductName} → ${supplier.supplier_name} (qty ${result.order_qty}).`
          : `Cleared supplier from ${row.ProductName}.`);
      })
      .catch((e) => setError(e.message))
      .finally(() => { setAssigningCode(null); loadWorkflow(); });
  };

  // Unassign a row directly from Supplier Order Details (Assigned view) --
  // same toggle endpoint toggleAssign uses (status 1 -> 0, clears OrSupplier),
  // just without needing to switch Process to By Supplier first. Drops the
  // row from the local `assigned` list on success so it disappears from THIS
  // supplier's list immediately; it's open again for any supplier to pick up.
  const unassignRow = (row) => {
    if (!store || !supplier) return;
    setAssigningCode(row.ProductCode); setBanner('');
    api.legacyAssignSupplier(store, row.ProductCode, supplier.supplier_code, supplier.supplier_name, session)
      .then(() => {
        setAssigned((cur) => cur.filter((r) => r.ProductCode !== row.ProductCode));
        setBanner(`Unassigned ${row.ProductName} from ${supplier.supplier_name}.`);
      })
      .catch((e) => setError(e.message))
      .finally(() => { setAssigningCode(null); loadWorkflow(); });
  };

  // Export the current supplier's order to Excel via the same backend route
  // the web Order Workspace uses (order_export.py) -- a direct port of the
  // legacy Form1.btnExport_Click -> ExportSelectedColumnsFromGrid sequence
  // (columns, S.No./OrderQty cell fills, Category prediction, filename
  // pattern, and row-count "Split" into separate files zipped together).
  // Export now ONLY includes rows already explicitly Assigned to this
  // supplier (status=1) -- it no longer bulk-assigns remaining open rows,
  // so picking a supplier and exporting can no longer silently close out
  // products the operator never actually assigned.
  // Only available from By Supplier / Assigned, matching the legacy app
  // (btnExport was only ever wired for supplier-scoped grids; Qty Check
  // explicitly hides it, and there's no supplier-scoped grid behind Review
  // All to export from).
  // Selected export columns, in OW_EXPORT_COLUMN_DEFS order, as the backend
  // column keys it expects (camelCase UI key -> snake_case API key).
  const OW_EXPORT_KEY_MAP = {
    productCode: 'product_code', productName: 'product_name', orderQty: 'order_qty',
    saleUnit: 'sale_unit', mrp: 'mrp', discount: 'discount', category: 'category',
    subLocation: 'sub_location', rack: 'rack',
    supplierProductCode: 'supplier_product_code', supplierProductName: 'supplier_product_name'
  };
  const selectedExportColumns = OW_EXPORT_COLUMN_DEFS
    .filter((c) => c.required || exportSettings.columns[c.key])
    .map((c) => OW_EXPORT_KEY_MAP[c.key]);

  const runExport = async () => {
    if (!supplier) { setError('Pick a supplier first.'); return; }
    // From the By Supplier grid, export assigns + includes ONLY the product
    // codes still in the grid (filteredRows already drops any row the operator
    // deleted via removedCodes), so a deleted row is neither assigned nor
    // exported. From the Assigned view there's nothing to curate -- omit the
    // list and the backend just exports what's already assigned.
    setExporting(true); setError('');
    try {
      // Load-all curated the full open list, so tell the backend to re-resolve
      // the curated codes against the all-open set (not this supplier's match),
      // and treat it as a history-shape export.
      const mode = view === 'supplier' ? (loadAll ? 'history' : supplierMode) : 'history';
      const dateFolder = owExportDateFolder();
      // order_no is OrderHeaderDetails' short per-day sequence (1, 2, 3...),
      // the human-readable number the operator expects as the subfolder
      // name (e.g. "4"). order_id is a per-second generation TIMESTAMP
      // (e.g. 20261023115659) -- never meant to be read by a person, and
      // using it here was producing unreadable export subfolder names.
      const orderNo = workflow?.order_no != null ? String(workflow.order_no)
        : workflow?.order_id != null ? String(workflow.order_id) : dateFolder;
      // ProductCode round-trips through pyodbc as a float (e.g. 9810.0); the
      // backend's product_codes contract is list[str] and Pydantic v2 does
      // NOT coerce float->str, so sending the raw float 422s every time.
      // Strip a trailing ".0" so the string matches the backend's own
      // _format_product_code() normalization of the numeric DB value
      // (float 9810.0 -> "9810", not "9810.0") -- otherwise the server-side
      // intersection against `wanted` never matches and every row is dropped.
      const productCodes = view === 'supplier'
        ? filteredRows.map((r) => String(r.ProductCode).replace(/\.0$/, ''))
        : undefined;
      const { blob, filename: backendFilename, exportedCount } = await api.legacyExportOrder(
        store, supplier.supplier_code, supplier.supplier_name, mode, Number(splitCount) || 0, session,
        { columns: selectedExportColumns, fileFormat: exportSettings.fileFormat, orderNo, productCodes, allProducts: view === 'supplier' && loadAll, images: exportSettings.images }
      );
      // Standard filename: "<supplier name> <ddmmyyyy> <order no>.<ext>",
      // written to D:\Export Order\<ddmmyyyy>\<order no>\ (or the operator's
      // chosen base path) when running inside Electron — falls back to a
      // normal browser download on the web build, where there is no
      // filesystem to write to directly (and no fixed naming convention to
      // enforce, since the operator picks the save location themselves).
      // A split export comes back as a .zip of parts -- keep the backend's
      // own name in that case rather than forcing a single xlsx/csv name
      // onto an archive.
      const ext = ['csv', 'xlsx'].includes(exportSettings.fileFormat) ? exportSettings.fileFormat : 'xls';
      // Legacy VB: <supplier> <store name>   <ddMMyyyy> (3 spaces before the date).
      const filename = `${owSafeFileName(`${supplier.supplier_name} ${store}   ${dateFolder}`)}.${ext}`;
      const folderParts = [exportSettings.basePath, dateFolder, owSafePathSegment(orderNo)];
      if (exportSettings.supplierWise) folderParts.push(owSafePathSegment(supplier.supplier_name));
      const written = [];
      const savedTo = await owSaveExport(blob, backendFilename, filename, folderParts.join('\\'), written);
      setLastExport(written.length ? {
        files: written, rememberKey: `supplier:${supplier.supplier_code}`, defaultChat: supplier.supplier_name,
        title: `Send ${supplier.supplier_name} order on WhatsApp`, source: 'Order'
      } : null);
      setBanner(savedTo
        ? `Exported ${exportedCount} product(s) for ${supplier.supplier_name} → ${savedTo}`
        : `Exported ${exportedCount} product(s) for ${supplier.supplier_name}.`);
      setExportOpen(false);
      setReloadTick((t) => t + 1);
    } catch (e) {
      setError(e.message || 'Export failed.');
    } finally {
      setExporting(false);
    }
  };

  // Pending export is read-only (no supplier, no assignment, nothing
  // changes server-side besides building the file) -- same Split/File-type/
  // Save-folder options as runExport, but always the grid's own fixed
  // column set (no per-column picker, no supplier subfolder: see
  // showColumns/showSupplierWise on OwExportCard).
  const runPendingExport = async () => {
    setExporting(true); setError('');
    try {
      const dateFolder = owExportDateFolder();
      const orderNo = workflow?.order_no != null ? String(workflow.order_no)
        : workflow?.order_id != null ? String(workflow.order_id) : dateFolder;
      const { blob, filename: backendFilename, exportedCount } = await api.legacyExportPendingOrder(
        store, Number(splitCount) || 0, session,
        { fileFormat: exportSettings.fileFormat, orderNo, images: exportSettings.images }
      );
      const ext = ['csv', 'xlsx'].includes(exportSettings.fileFormat) ? exportSettings.fileFormat : 'xls';
      const filename = `Pending ${dateFolder} ${owSafePathSegment(orderNo)}.${ext}`;
      const folderParts = [exportSettings.basePath, dateFolder, owSafePathSegment(orderNo)];
      const written = [];
      const savedTo = await owSaveExport(blob, backendFilename, filename, folderParts.join('\\'), written);
      setLastExport(written.length ? {
        files: written, rememberKey: 'pending', defaultChat: '', title: 'Send pending order on WhatsApp', source: 'Pending order'
      } : null);
      setBanner(savedTo ? `Exported ${exportedCount} pending product(s) → ${savedTo}` : `Exported ${exportedCount} pending product(s).`);
      setExportOpen(false);
    } catch (e) {
      setError(e.message || 'Export failed.');
    } finally {
      setExporting(false);
    }
  };

  // The supplier confirms some assigned lines are out of stock after the
  // order's already gone out. Rather than unassigning each one by hand,
  // this checks the supplier's own live stock (SupplierStock.Stock) for
  // every currently-Assigned line and drops whichever has none -- back to
  // open (status=0, qtycheck=1, no supplier) so another supplier can pick
  // them up without re-triggering Qty Check review.
  const removeUnavailable = () => {
    if (!store || !supplier) return;
    if (!window.confirm(`Check ${supplier.supplier_name}'s stock and remove any assigned products they don't have? This unassigns them (qty-checked, open for other suppliers).`)) return;
    setRemovingUnavailable(true); setError('');
    api.legacyRemoveUnavailable(store, supplier.supplier_code, session)
      .then(({ removed_count }) => {
        setBanner(removed_count
          ? `Removed ${removed_count} out-of-stock product(s) from ${supplier.supplier_name}.`
          : `${supplier.supplier_name} has stock for every assigned product -- nothing removed.`);
        setReloadTick((t) => t + 1);
      })
      .catch((e) => setError(e.message))
      .finally(() => setRemovingUnavailable(false));
  };

  const activeCount = view === 'qty' ? filteredQty.length
    : view === 'pending' ? filteredPending.length
      : view === 'assigned' ? filteredAssigned.length
        : filteredRows.length;

  // The line panel reads only the loader that is on screen. A previous
  // store's or process's rows must not fill in a product that this grid
  // has already cleared.
  const activeLineRow = useMemo(() => {
    if (selectedCode == null) return null;
    if (view === 'qty') return qtyRows.find((r) => r.productcode === selectedCode) || null;
    if (view === 'pending') return pendingRows.find((r) => r.productcode === selectedCode) || null;
    if (view === 'assigned') return assigned.find((r) => r.ProductCode === selectedCode) || null;
    return rows.find((r) => r.ProductCode === selectedCode) || null;
  }, [view, selectedCode, qtyRows, pendingRows, rows, assigned]);
  const line = useMemo(() => {
    if (!activeLineRow) return null;
    const lower = view === 'qty' || view === 'pending';
    const code = lower ? activeLineRow.productcode : activeLineRow.ProductCode;
    return owLineFromRow(view, activeLineRow, {
      edit: edits[code],
      reviewed: reviewedCodes.has(code),
      qtyChecked: qtyCheckedHere.has(code),
      assignedStatus: lower ? null : (statusOverride[code] ?? activeLineRow.Status),
      supplierName: supplier?.supplier_name || null,
      stockMode: isStockMode,
    });
  }, [view, activeLineRow, edits, reviewedCodes, qtyCheckedHere, statusOverride, supplier, isStockMode]);
  const summary = useMemo(() => {
    const lower = view === 'qty' || view === 'pending';
    const listed = view === 'qty' ? filteredQty : view === 'pending' ? filteredPending : view === 'assigned' ? filteredAssigned : filteredRows;
    return owWorkspaceSummary({
      loading,
      rows: listed,
      qtyOf: (row) => {
        const code = lower ? row.productcode : row.ProductCode;
        const edited = edits[code];
        if (edited != null && edited !== '') return edited;
        return lower ? row.orderqty : row.OrderQty;
      },
      originalOf: (row) => (lower ? row.orgorderqty : row.OrgOrderQty),
      offerOf: (row) => Boolean(row.IsOffer),
      qtyCheckedOf: (row) => {
        if (view === 'qty') return reviewedCodes.has(row.productcode) ? 'checked' : 'pending';
        if (view === 'pending') return 'checked';
        const raw = row.Qtycheck;
        const local = qtyCheckedHere.has(row.ProductCode);
        if (raw === null || raw === undefined) return local ? 'checked' : 'unknown';
        return (Number(raw) === 1 || local) ? 'checked' : 'pending';
      },
      workflow,
    });
  }, [view, loading, filteredQty, filteredPending, filteredAssigned, filteredRows, edits, reviewedCodes, qtyCheckedHere, workflow]);

  // Close the settings card when switching grids (each grid has its own config).
  useEffect(() => { setSettingsFor(null); }, [view]);
  useEffect(() => { if (view !== 'supplier' && view !== 'assigned' && view !== 'pending') setExportOpen(false); }, [view]);
  useEffect(() => { if (view !== 'supplier') setLoadAll(false); }, [view]);
  // One settings button per grid now (not just Qty Check/Review All) -- see
  // OW_GRID_SETTINGS_META for the {title, base} each view's ⚙ button opens.
  const gridId = view;
  const openProductInfo = (code) => { setSelectedCode(code); setInfoCode(code); };
  // Previous Decisions panel shown in the layout -> no info button; hidden ->
  // the button opens the same history as a card.
  const historyPanelShown = owLayout.panels.some((p) => p.key === 'history' && !p.hidden);
  // Qty Check status: a tick (✓ checked / – pending) by default; the grid
  // settings' "Qty check: Text" shows the word badge instead.
  const owQtyCheckCell = (status) => (owLayout.qtyCheckStyle === 'text'
    ? <span className={`ow-qtycheck-badge ow-qtycheck-${status}`}>{OW_QTYCHECK_STATUS_LABEL[status]}</span>
    : <span className={`ow-qtycheck-mark ow-qtycheck-mark--${status}`} title={OW_QTYCHECK_STATUS_LABEL[status]}>{status === 'checked' ? '✓' : status === 'pending' ? '–' : '?'}</span>);
  const productNameCell = (raw, code) => (
    <span className="ow-name-wrap">
      <span className="ow-cellname" title={raw}>{owCleanName(raw)}</span>
      <AbnormalMark info={abnormal.byCode[String(code)]} />
      {!historyPanelShown && <button
        type="button"
        className="ow-row-info"
        title="Line details and previous orders"
        aria-label={`Details for ${owCleanName(raw) || code}`}
        onClick={(e) => { e.stopPropagation(); openProductInfo(code); }}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M11 10h2v7h-2v-7Zm0-3h2v2h-2V7Zm1-5a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm0 2a8 8 0 1 1 0 16 8 8 0 0 1 0-16Z" /></svg>
      </button>}
    </span>
  );
  const qtyCols = resolveOwColumns(OW_QTY_COLUMNS, owColCfg.qty);
  const reviewCols = resolveOwColumns(OW_REVIEW_COLUMNS, owColCfg.review);
  const pendingCols = resolveOwColumns(OW_PENDING_COLUMNS, owColCfg.pending);
  const assignedCols = resolveOwColumns(OW_ASSIGNED_COLUMNS, owColCfg.assigned);

  function renderQtyCell(col, row, index, reviewed) {
    switch (col.key) {
      case 'sno': return index + 1;
      case 'name': return productNameCell(row.productname, row.productcode);
      case 'qtycheckstatus': {
        const status = reviewed ? 'checked' : 'pending';
        return owQtyCheckCell(status);
      }
      case 'offer': return row.IsOffer ? <span title="Has had a free-qty offer in purchase history">🎁</span> : null;
      case 'orqty': {
        const value = edits[row.productcode] ?? row.orderqty;
        const org = row.orgorderqty;
        const tone = owQtyDiffTone(org, value);
        return (
          <span className="ow-qty-cell">
            <input ref={(el) => { qtyRefs.current[index] = el; }} className={`ow-qty${tone ? ` ow-qty-${tone}` : ''}`} type="number" min={0} step={1} inputMode="numeric" aria-label={`${row.productname} order quantity`}
              value={value} disabled={savingCode === row.productcode || finalized}
              onClick={(e) => e.stopPropagation()} onFocus={(e) => { setSelectedCode(row.productcode); e.target.select(); }}
              onChange={(e) => setEdits((cur) => ({ ...cur, [row.productcode]: owWholeQty(e.target.value) }))}
              onKeyDown={(e) => onQtyKey(e, row, index)} />
            <span className="ow-qty-diff-slot">
              {tone && <OwQtyDiffArrow from={org} to={value} />}
            </span>
          </span>
        );
      }
      case 'stock': return <span className={Number(row.totalstock) === 0 ? 'ow-stock-zero' : undefined}>{fmtOwQty(row.totalstock)}</span>;
      case 'pack': return fmtOwQty(row.saleunit);
      case 'desc': return row.unitdescription;
      case 'slsqty': return fmtOwQty(row.slsqty);
      case 'mrp': return fmtOwMoney(row.mrp);
      case 'lrdate': return fmtOwDaysAgo(row.lastreceiveddate);
      case 'lsdate': return fmtOwDaysAgo(row.lastsaledate);
      case 'maxqty': return fmtOwQty(row.maxsaleqty);
      case 'wanted': return row.wantedtype ?? '—';
      default: return null;
    }
  }
  function renderPendingCell(col, row, index) {
    switch (col.key) {
      case 'sno': return index + 1;
      case 'name': return productNameCell(row.productname, row.productcode);
      case 'qtycheckstatus': {
        const status = 'checked';
        return owQtyCheckCell(status);
      }
      case 'offer': return row.IsOffer ? <span title="Has had a free-qty offer in purchase history">🎁</span> : null;
      case 'orqty': {
        const value = edits[row.productcode] ?? row.orderqty;
        const tone = owQtyDiffTone(row.orgorderqty, value);
        return (
          <span className="ow-qty-cell">
            <input ref={(el) => { pendingQtyRefs.current[index] = el; }} className={`ow-qty${tone ? ` ow-qty-${tone}` : ''}`} type="number" min={0} step={1} inputMode="numeric" aria-label={`${row.productname} order quantity`}
              value={value} disabled={savingCode === row.productcode || finalized}
              onClick={(e) => e.stopPropagation()} onFocus={(e) => { setSelectedCode(row.productcode); e.target.select(); }}
              onChange={(e) => setEdits((cur) => ({ ...cur, [row.productcode]: owWholeQty(e.target.value) }))}
              onKeyDown={(e) => onPendingQtyKey(e, row, index)} />
            <span className="ow-qty-diff-slot">
              {tone && <OwQtyDiffArrow from={row.orgorderqty} to={value} />}
            </span>
          </span>
        );
      }
      case 'stock': return <span className={Number(row.totalstock) === 0 ? 'ow-stock-zero' : undefined}>{fmtOwQty(row.totalstock)}</span>;
      case 'pack': return fmtOwQty(row.saleunit);
      case 'desc': return row.unitdescription;
      case 'slsqty': return fmtOwQty(row.slsqty);
      case 'mrp': return fmtOwMoney(row.mrp);
      case 'maxqty': return fmtOwQty(row.maxsaleqty);
      case 'wanted': return row.wantedtype ?? '—';
      default: return null;
    }
  }
  function renderReviewCell(col, row, index) {
    switch (col.key) {
      case 'sno': return index + 1;
      case 'name': return productNameCell(row.ProductName, row.ProductCode);
      case 'qtycheckstatus': {
        const status = owQtyCheckStatus(row);
        return owQtyCheckCell(status);
      }
      case 'offer': return row.IsOffer ? <span title="Has had a free-qty offer in purchase history">🎁</span> : null;
      case 'orqty': {
        const value = edits[row.ProductCode] ?? row.OrderQty;
        const tone = owQtyDiffTone(row.OrgOrderQty, value);
        return (
          <span className="ow-qty-cell">
            <input ref={(el) => { reviewQtyRefs.current[index] = el; }} className={`ow-qty${tone ? ` ow-qty-${tone}` : ''}`} type="number" min={0} step={1} inputMode="numeric" aria-label={`${row.ProductName} order quantity`}
              value={value} disabled={savingCode === row.ProductCode || finalized}
              onClick={(e) => e.stopPropagation()} onFocus={(e) => { setSelectedCode(row.ProductCode); e.target.select(); }}
              onChange={(e) => setEdits((cur) => ({ ...cur, [row.ProductCode]: owWholeQty(e.target.value) }))}
              onBlur={(e) => { if (!skipBlurSaveRef.current) saveOrderQty(row, owWholeQty(e.target.value)); }}
              onKeyDown={(e) => {
                if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                  skipBlurSaveRef.current = true;
                  requestAnimationFrame(() => { skipBlurSaveRef.current = false; });
                }
                owHandleRowArrowKeys(e, reviewQtyRefs, index);
              }} />
            <span className="ow-qty-diff-slot">
              {tone && <OwQtyDiffArrow from={row.OrgOrderQty} to={value} />}
            </span>
          </span>
        );
      }
      case 'stock': return <span className={Number(row.TotalStock) === 0 ? 'ow-stock-zero' : undefined}>{fmtOwQty(row.TotalStock)}</span>;
      case 'pack': return fmtOwQty(row.SaleUnit);
      case 'desc': return row.UnitDescription;
      case 'sls': return fmtOwQty(row.SLSQty);
      case 'mrp': return fmtOwMoney(row.MRP);
      case 'wanted': return row.WantedType ?? '—';
      default: return null;
    }
  }
  function renderSupplierCell(col, row, index, isAssigned, reviewed, value) {
    switch (col.key) {
      case 'sno': return index + 1;
      case 'name': return productNameCell(row.ProductName, row.ProductCode);
      case 'offer': return row.IsOffer ? <span title="Has had a free-qty offer in purchase history">🎁</span> : null;
      case 'check': return reviewed && <span className="ow-reviewed-check" title="Already qty-checked">✓</span>;
      case 'qtycheckstatus': {
        const status = owQtyCheckStatus(row);
        return owQtyCheckCell(status);
      }
      case 'orqty': {
        const tone = (reviewed || Number(value) !== Number(row.OrderQty)) ? owQtyDiffTone(row.OrgOrderQty, value) : '';
        return (
        <span className="ow-qty-cell">
          <input ref={(el) => { supplierQtyRefs.current[index] = el; }} className={`ow-qty${tone ? ` ow-qty-${tone}` : ''}`} type="number" min={0} step={1} inputMode="numeric" aria-label={`${row.ProductName} order quantity`}
            value={value} disabled={savingCode === row.ProductCode || isAssigned || finalized}
            onClick={(e) => e.stopPropagation()} onFocus={(e) => { setSelectedCode(row.ProductCode); e.target.select(); }}
            onChange={(e) => setEdits((cur) => ({ ...cur, [row.ProductCode]: owWholeQty(e.target.value) }))}
            onBlur={(e) => { if (!skipBlurSaveRef.current) saveOrderQty(row, owWholeQty(e.target.value)); }}
            onKeyDown={(e) => {
              // Enter with a supplier selected assigns (toggleAssign itself
              // saves a pending qty edit first, so the two never race).
              // With no supplier picked, Enter still commits the qty edit
              // on its own -- same as VB.NET's CellEndEdit, independent of
              // assignment.
              if (e.key === '+' || e.key === '-') {
                e.preventDefault();
                const current = owWholeQty(e.target.value);
                const next = e.key === '+' ? current + 1 : Math.max(0, current - 1);
                setEdits((cur) => ({ ...cur, [row.ProductCode]: next }));
              } else if (e.key === 'Enter') {
                e.preventDefault();
                if (!isAssigned && supplier) { toggleAssign(row); return; }
                const v = owWholeQty(e.target.value);
                if (v !== row.OrderQty) saveOrderQty(row, v);
              } else if (e.key === 'Delete') { e.preventDefault(); removeRow(row.ProductCode, index); }
              else if (e.key === 'Escape' || (e.key === 'Backspace' && owIsClearKeypress(e))) {
                e.preventDefault();
                commitSupplierQty(row, 0, Math.min(index + 1, filteredRows.length - 1));
              }
              else if (e.key === 'ArrowDown') {
                e.preventDefault();
                commitSupplierQty(row, owWholeQty(e.target.value), Math.min(index + 1, filteredRows.length - 1));
              } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                commitSupplierQty(row, owWholeQty(e.target.value), Math.max(index - 1, 0));
              }
            }} />
          <span className="ow-qty-diff-slot">
            {tone && <OwQtyDiffArrow from={row.OrgOrderQty} to={value} />}
          </span>
        </span>
        );
      }
      case 'stock': return <span className={Number(row.TotalStock) === 0 ? 'ow-stock-zero' : undefined}>{fmtOwQty(row.TotalStock)}</span>;
      case 'pack': return fmtOwQty(row.SaleUnit);
      case 'desc': return row.UnitDescription;
      case 'slsqty': return fmtOwQty(row.SLSQty);
      case 'mrp': return fmtOwMoney(row.MRP);
      case 'sstock': return <span className="ow-sstock-val" title="Supplier's own live stock (SupplierStock.Stock)">{fmtOwQty(row.S_Stock)}</span>;
      case 'disc': return fmtOwQty(row.Discount);
      case 'minqty': return fmtOwQty(row.MinQty);
      case 'rack': return row.Rack || '—';
      case 'wanted': return row.WantedType ?? '—';
      case 'action': return (
        <>
          <button type="button" className={`ow-btn ow-btn-sm ${isAssigned ? 'ow-btn-danger' : 'ow-btn-primary'}`} disabled={!supplier || assigningCode === row.ProductCode || finalized}
            onClick={(e) => { e.stopPropagation(); toggleAssign(row); }}>
            {assigningCode === row.ProductCode ? '…' : isAssigned ? 'Unassign' : 'Assign'}
          </button>
          {!isAssigned && (
            <button type="button" className="ow-btn ow-btn-sm" title="Remove from this list (Delete) -- stays available to assign to another supplier" aria-label={`Remove ${row.ProductName} from this list`}
              onClick={(e) => { e.stopPropagation(); removeRow(row.ProductCode, index); }}>
              ✕
            </button>
          )}
        </>
      );
      default: return null;
    }
  }
  function renderAssignedCell(col, row, index) {
    switch (col.key) {
      case 'sno': return index + 1;
      case 'name': return productNameCell(row.ProductName, row.ProductCode);
      case 'offer': return row.IsOffer ? <span title="Has had a free-qty offer in purchase history">🎁</span> : null;
      case 'orqty': return fmtOwQty(row.OrderQty);
      case 'stock': return <span className={Number(row.TotalStock) === 0 ? 'ow-stock-zero' : undefined}>{fmtOwQty(row.TotalStock)}</span>;
      case 'pack': return fmtOwQty(row.SaleUnit);
      case 'desc': return row.UnitDescription;
      case 'slsqty': return fmtOwQty(row.SLSQty);
      case 'mrp': return fmtOwMoney(row.MRP);
      case 'wanted': return row.WantedType ?? '—';
      case 'qtycheckstatus': {
        const status = owQtyCheckStatus(row);
        return owQtyCheckCell(status);
      }
      case 'remarks': return row.Remarks ?? '—';
      case 'action': return (
        <button type="button" className="ow-btn ow-btn-sm ow-btn-danger" disabled={assigningCode === row.ProductCode || finalized}
          onClick={(e) => { e.stopPropagation(); unassignRow(row); }}>
          {assigningCode === row.ProductCode ? '…' : 'Unassign'}
        </button>
      );
      default: return null;
    }
  }

  const owHistorySection = (
    <section className="ow-panel ow-panel--history">
      <div className="ow-panel-title">Previous Decisions{selectedCode != null && history.length > 0 && <span className="ow-panel-count">Last {Math.min(history.length, 25)}</span>}</div>
      <div className="ow-panel-scroll">
        <table className="ow-intel-table ow-fixed">
          <colgroup>
            <col style={{ width: '11%' }} /><col style={{ width: '11%' }} /><col style={{ width: '11%' }} /><col style={{ width: '13%' }} /><col style={{ width: '24%' }} /><col style={{ width: '14%' }} /><col style={{ width: '9%' }} /><col style={{ width: '7%' }} />
          </colgroup>
          <thead><tr><th className="ow-num">Or Qty</th><th className="ow-num">Org Order</th><th className="ow-num">Pack</th><th className="ow-num">MRP</th><th>Remarks</th><th>Wanted Date</th><th>Wanted</th><th>Or Supplier</th></tr></thead>
          <tbody>
            {history.map((row, i) => (
              <tr key={i}><td className="ow-num">{fmtOwQty(row.Orqty)}</td><td className="ow-num">{fmtOwQty(row.OrgOrderQty)}</td><td className="ow-num">{fmtOwQty(row.saleunit)}</td><td className="ow-num">{fmtOwMoney(row.MRP)}</td><td>{row.remarks ?? '—'}</td><td>{fmtOwDate(row.Wanteddate)}</td><td>{row.WantedType ?? '—'}</td><td>{row.Orsupplier ?? '—'}</td></tr>
            ))}
            {!history.length && <tr><td colSpan={8} className="ow-empty">{selectedCode == null ? 'Select a product to see its previous-order history.' : historyLoading ? 'Loading…' : 'No previous-order history for this product.'}</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  );
  const owVisiblePanels = owLayout.panels.filter((p) => !p.hidden);
  const owSidePanels = owVisiblePanels.filter((p) => p.dock === 'side');
  const owBottomPanels = owVisiblePanels.filter((p) => p.dock === 'bottom');
  const owSideShown = !owLayout.sideHidden && owSidePanels.length > 0;
  // One OrderIntelligence per panel: each fetches through the shared
  // owIntelCache, so splitting panels across docks costs no extra requests
  // and a detail fetch never re-renders the big grid.
  const priceSourceKey = owVisiblePanels.some((p) => p.key === 'purchase') ? 'purchase' : owVisiblePanels[0]?.key;
  const renderOwPanel = (p) => (p.key === 'history' ? <Fragment key="history">{owHistorySection}</Fragment> : (
    <OrderIntelligence
      key={p.key}
      sections={[p.key]}
      store={store}
      productCode={selectedCode}
      visibleCodes={owVisibleCodes}
      mode="local"
      session={session}
      onError={setError}
      onLatest={p.key === priceSourceKey ? (info) => {
        if (info == null || String(info.code) !== String(selectedCode)) return;
        setLinePrices((cur) => (cur && cur.code === info.code && cur.cost === info.cost && cur.ptr === info.ptr && cur.discount === info.discount && cur.grnDate === info.grnDate && cur.supplier === info.supplier && cur.lastSaleDate === info.lastSaleDate && cur.freeQty === info.freeQty && cur.receivedQty === info.receivedQty ? cur : info));
      } : undefined}
      onPurchaseSelect={(row) => setOwRecord({ kind: 'purchase', row, productCode: selectedCode })}
      onSalesSelect={(row) => setOwRecord({ kind: 'sales', row, productCode: selectedCode })}
    />
  ));

  const processOption = (view === 'supplier'
    ? OW_PROCESS_OPTIONS.find((p) => p.view === 'supplier' && p.supplierMode === supplierMode)
    : OW_PROCESS_OPTIONS.find((p) => p.view === view && (p.pendingScope || 'order') === (view === 'pending' ? pendingScope : 'order'))) || OW_PROCESS_OPTIONS[0];
  const lineNote = owLineNote(line, view, { finalized });
  let orderContext = 'Loading order…';
  if (!store) orderContext = 'No store';
  else if (orderHeaderError) orderContext = 'Order info unavailable';
  else if (orderHeader && orderHeader.order_id == null) orderContext = 'No active order';
  else if (orderHeader) orderContext = `Order #${orderHeader.order_no ?? orderHeader.order_id}`;
  const orderUpdated = orderHeader && orderHeader.updated_at ? fmtOwDateTime(orderHeader.updated_at) : '';

  return (
    <section className={`screen-panel ow-screen ow-proc ow-rows-${owLayout.rowSize} ow-weight-${owLayout.rowWeight}${hidden ? ' ow-screen-hidden' : ''}`}>
      <div className="ow-toolbar ow-command">
        <div className="ow-identity">
          <span className="ow-kicker">Nexora Procurement</span>
          <h2 className="ow-title">Order Workspace</h2>
        </div>
        <label className="ow-field">
          <span>Store</span>
          <select className="ow-store-select" value={store} onChange={(e) => setStore(e.target.value)}>
            {!stores.length && <option value="">No stores</option>}
            {stores.map((s) => <option key={s.store_name} value={s.store_name}>{s.store_name}</option>)}
          </select>
        </label>
        <span className="ow-sep" aria-hidden="true" />
        <label className="ow-field">
          <span>Process</span>
          <select
            className="ow-process-select"
            aria-label="Process"
            value={view === 'qty' && abnormalOnly ? OW_ABNORMAL_PROCESS_KEY : (
              (view === 'supplier'
                ? OW_PROCESS_OPTIONS.find((p) => p.view === 'supplier' && p.supplierMode === supplierMode)
                : OW_PROCESS_OPTIONS.find((p) => p.view === view && (p.pendingScope || 'order') === (view === 'pending' ? pendingScope : 'order'))
              )?.key || 'qty_check'
            )}
            onChange={(e) => {
              if (e.target.value === OW_ABNORMAL_PROCESS_KEY) { setView('qty'); setAbnormalOnly(true); return; }
              const opt = OW_PROCESS_OPTIONS.find((p) => p.key === e.target.value);
              if (!opt) return;
              setAbnormalOnly(false);
              setView(opt.view);
              if (opt.supplierMode) setSupplierMode(opt.supplierMode);
              if (opt.view === 'pending') setPendingScope(opt.pendingScope || 'order');
            }}
          >
            {OW_PROCESS_OPTIONS.map((p) => (
              <Fragment key={p.key}>
                <option value={p.key}>{p.label}</option>
                {p.key === 'qty_check' && (abnormal.items.length > 0 || abnormal.loading || abnormalOnly) && (
                  <option value={OW_ABNORMAL_PROCESS_KEY}>
                    {`⚠ Qty Check · Abnormal sales (${abnormal.loading ? '…' : abnormal.abnormalCount})`}
                  </option>
                )}
              </Fragment>
            ))}
          </select>
        </label>
        {(view === 'supplier' || view === 'assigned') && (
          <label className="ow-field">
            <span>Supplier</span>
            <OwSupplierPicker suppliers={suppliers} value={supplier} onChange={setSupplier} />
          </label>
        )}
        {view === 'supplier' && (
          <div className="ow-tabs" role="tablist" aria-label="Supplier mode">
            <button type="button" role="tab" aria-selected={!loadAll && supplierMode === 'history'} disabled={loadAll} className={!loadAll && supplierMode === 'history' ? 'active' : ''} onClick={() => setSupplierMode('history')}>History</button>
            <button type="button" role="tab" aria-selected={!loadAll && supplierMode === 'stock'} disabled={loadAll} className={!loadAll && supplierMode === 'stock' ? 'active' : ''} onClick={() => setSupplierMode('stock')}>Live Stock</button>
          </div>
        )}
        {view === 'supplier' && (
          <button type="button"
            className={`ow-btn ow-btn-sm ow-loadall-toggle${loadAll ? ' active' : ''}`}
            aria-pressed={loadAll}
            title="Load every open orderable product (not just this supplier's history/stock match), so you can still assign a product the match missed"
            onClick={() => setLoadAll((v) => !v)}>
            {loadAll ? '✓ All products' : 'Load all products'}
          </button>
        )}
        <button type="button"
          className={`ow-btn ow-btn-sm ow-filters-toggle${filtersOpen ? ' active' : ''}`}
          aria-pressed={filtersOpen}
          title="Show/hide a per-column filter box in the grid header"
          onClick={() => setFiltersOpen((v) => !v)}>
          {filtersOpen ? '✓ Filters' : 'Filters'}
        </button>
        <label className="ow-field">
          <span>Product type</span>
          <select className="ow-type-select" value={productType} onChange={(e) => setProductType(e.target.value)} aria-label="Product type">
            <option value="All">All</option>
            <option value="Pharma">Pharma</option>
            <option value="Non Pharma">Non Pharma</option>
          </select>
        </label>
        {(view === 'qty' || view === 'pending' || view === 'review' || view === 'supplier' || view === 'assigned') && (
          <label className="ow-field">
            <span>Wanted</span>
            <select className="ow-wanted-select" value={wantedFilter} onChange={(e) => setWantedFilter(e.target.value)} aria-label="Wanted type filter" title={wantedFilter}>
              <option value="All">All</option>
              {wantedOptions.map((w) => <option key={w} value={w}>{w}</option>)}
            </select>
          </label>
        )}
        <input
          className="ow-search"
          type="search"
          placeholder="Search product or code"
          aria-label="Search products"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <span className="ow-context" title={orderUpdated ? `Order data updated ${orderUpdated}` : undefined}>
          {orderContext}{orderUpdated ? ` · ${orderUpdated}` : ''}
        </span>
        <span className="ow-command-actions">
        <button type="button" className="ow-btn" disabled={!store || loading} title="Reload this store from the server" onClick={() => { setReloadTick((t) => t + 1); loadWorkflow(); }}>
          {loading ? 'Loading…' : 'Reload'}
        </button>
        {(view === 'qty' || view === 'review' || view === 'pending' || view === 'supplier' || view === 'assigned') && (
          <button type="button" ref={settingsBtnRef} className="ow-icon-btn" title="Grid column settings" aria-label="Grid column settings" aria-expanded={Boolean(settingsFor)} onClick={() => setSettingsFor((v) => (v ? null : gridId))}>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d={OW_GEAR_PATH} /></svg>
          </button>
        )}
        {finalized
          ? <button type="button" className="ow-btn" onClick={() => finalize(true)}>Reopen</button>
          : <button type="button" className="ow-btn ow-btn-primary" disabled={!workflow?.ready} title={workflow?.ready ? 'Lock this order' : 'Complete review first'} onClick={() => finalize(false)}>Finalize</button>}
        {view === 'assigned' && (
          <button type="button" className="ow-btn" disabled={!supplier || removingUnavailable}
            title={supplier ? "Check this supplier's stock and unassign anything they don't have" : 'Pick a supplier first'}
            onClick={removeUnavailable}>
            {removingUnavailable ? 'Checking…' : 'Remove Out-of-Stock'}
          </button>
        )}
        {(view === 'supplier' || view === 'assigned') && (
          <button type="button" ref={exportBtnRef} className="ow-btn" disabled={!supplier} title={supplier ? 'Export order to Excel' : 'Pick a supplier first'} aria-expanded={exportOpen} onClick={() => setExportOpen((v) => !v)}>⬇ Export</button>
        )}
        {view === 'pending' && pendingScope !== 'rejected' && (
          <button type="button" ref={exportBtnRef} className="ow-btn" title="Export pending (reviewed, not yet assigned) products to Excel" aria-expanded={exportOpen} onClick={() => setExportOpen((v) => !v)}>⬇ Export</button>
        )}
        </span>
      </div>
      <div className="ow-summary" aria-live="polite">
        <span className="ow-summary-mode">{processOption.label}</span>
        {view === 'bulkassign' ? (
          <span className="ow-summary-loading">Best margin over the last 5 supplies · not received → most frequent supplier</span>
        ) : summary.loading ? (
          <span className="ow-summary-loading">Loading {processOption.label}…</span>
        ) : (
          <>
            <div className="ow-stat"><span>Products</span><b>{summary.products}</b></div>
            {summary.originalQty != null && (
              <div className="ow-stat" title="Sum of original quantities on the rows now listed"><span>Original qty</span><b>{fmtOwQty(summary.originalQty)}</b></div>
            )}
            <div className="ow-stat" title="Sum of final quantities on the rows now listed, including unsaved edits"><span>Final qty</span><b>{summary.finalQty == null ? '—' : fmtOwQty(summary.finalQty)}</b></div>
            {summary.qtyCheckKnown != null && (
              <div className="ow-stat" title="Qty Check saved on the rows now listed"><span>Qty Check</span><b>{summary.qtyCheckChecked}/{summary.qtyCheckKnown}</b></div>
            )}
            {summary.pendingLines != null && <div className="ow-stat" title="From the order workflow for this store"><span>Pending</span><b>{fmtOwQty(summary.pendingLines)}</b></div>}
            {summary.assignedLines != null && <div className="ow-stat" title="From the order workflow for this store"><span>Assigned</span><b>{fmtOwQty(summary.assignedLines)}</b></div>}
            {summary.openLines != null && <div className="ow-stat" title="From the order workflow for this store"><span>Open</span><b>{fmtOwQty(summary.openLines)}</b></div>}
            <div className="ow-stat"><span>Offers</span><b>{summary.offers}</b></div>
            <div className="ow-stat" title="Final quantity 0 means do not order"><span>Qty 0</span><b>{summary.zeroQty}</b></div>
            {summary.status && <span className={`ow-chip ${finalized || workflow?.ready ? 'ow-chip-ok' : 'ow-chip-run'}`}>{summary.status.replace(/_/g, ' ')}</span>}
          </>
        )}
      </div>
      {exportOpen && view === 'pending' && (
        <OwExportCard
          anchorRef={exportBtnRef}
          splitCount={splitCount}
          setSplitCount={setSplitCount}
          exporting={exporting}
          scopeLabel={`Pending (${filteredPending.length} product${filteredPending.length === 1 ? '' : 's'})`}
          onExport={runPendingExport}
          onClose={() => setExportOpen(false)}
          exportSettings={exportSettings}
          onUpdateExportSettings={updateExportSettings}
          headline="Read-only — no supplier assignment. Downloads every pending (reviewed, not yet assigned) product."
          showColumns={false}
          showSupplierWise={false}
        />
      )}
      {exportOpen && view !== 'pending' && (
        <OwExportCard
          anchorRef={exportBtnRef}
          splitCount={splitCount}
          setSplitCount={setSplitCount}
          exporting={exporting}
          scopeLabel={view === 'assigned' ? `${supplier?.supplier_name || 'selected supplier'} (assigned)` : `${supplier?.supplier_name || 'selected supplier'}`}
          onExport={runExport}
          onClose={() => setExportOpen(false)}
          exportSettings={exportSettings}
          onUpdateExportSettings={updateExportSettings}
        />
      )}
      {banner && (() => {
        // An export banner ends "... → <saved path>"; offer to open that file
        // (Excel) or folder straight from the banner.
        const savedPath = window.nexoraDesktop?.openExportPath ? (banner.split(' → ')[1] || '').trim() : '';
        const isFile = /\.(xls|xlsx|csv)$/i.test(savedPath);
        const openSaved = async () => {
          const err = await window.nexoraDesktop.openExportPath(savedPath);
          if (err) setError(`Could not open ${savedPath}: ${err}`);
        };
        return (
          <div className="ow-banner">
            <span>{banner}</span>
            {savedPath && <button type="button" className="ow-banner-open" onClick={openSaved}>{isFile ? 'Open in Excel' : 'Open folder'}</button>}
            {savedPath && lastExport && storeWhatsAppAvailable() && (
              <button type="button" className="ow-banner-open" onClick={() => setWaSendOpen(true)}>Send on WhatsApp</button>
            )}
            <button type="button" className="ow-banner-x" onClick={() => setBanner('')} aria-label="Dismiss">×</button>
          </div>
        );
      })()}
      {waSendOpen && lastExport && (
        <WhatsAppSendDialog
          {...lastExport}
          onClose={() => setWaSendOpen(false)}
          onSent={(chat) => setBanner(`Sent on WhatsApp to ${chat}.`)}
        />
      )}
      {settingsFor && (() => {
        // Per-grid {title, base columns} the ⚙ button opens -- 'supplier'
        // uses the CURRENT stock/history layout (owSupplierColumns(isStockMode)),
        // same base owColgroupPct/the grid's own <colgroup> already render.
        const meta = {
          qty: { title: 'Quantity Review', base: OW_QTY_COLUMNS },
          review: { title: 'Review All', base: OW_REVIEW_COLUMNS },
          pending: { title: 'Pending Order', base: OW_PENDING_COLUMNS },
          supplier: { title: 'By Supplier', base: supplierColsBase },
          assigned: { title: 'Supplier Order Details', base: OW_ASSIGNED_COLUMNS },
        }[settingsFor];
        if (!meta) return null;
        return (
          <OwGridSettings
            title={meta.title}
            anchorRef={settingsBtnRef}
            base={meta.base}
            cfg={owColCfg[settingsFor]}
            onToggle={(key) => cfgToggle(settingsFor, key)}
            onMove={(key, dir) => cfgMove(settingsFor, meta.base, key, dir)}
            onWidth={(key, w) => cfgWidth(settingsFor, key, w)}
            onReset={() => { cfgReset(settingsFor); setOwLayout(owNormalizeLayout(null)); }}
            onClose={() => setSettingsFor(null)}
            layout={owLayout}
            onLayout={(patch) => setOwLayout((l) => ({ ...l, ...patch }))}
          />
        );
      })()}

      {error && (
        <div className="ow-error" role="alert">
          {error}
          <button type="button" onClick={() => { setError(''); setReloadTick((t) => t + 1); loadWorkflow(); }} style={{ marginLeft: '0.6rem' }}>Retry</button>
          <button type="button" onClick={() => setError('')} aria-label="Dismiss">×</button>
        </div>
      )}

      <div className={`ow-body ow-side-${owSideShown ? owLayout.sidePosition : 'hidden'} ow-side-w-${owLayout.sideWidth} ow-bottom-${owLayout.bottomHeight}`}>
        <div className="ow-left">
        <div className="ow-main">
          <div className="ow-help">
            <span className="ow-status-hint">
              {view === 'qty' && <><kbd>Enter</kbd> Accept <kbd>Esc</kbd> Set 0 <kbd>↕</kbd> Navigate</>}
              {view === 'pending' && <><kbd>↕</kbd> Navigate</>}
              {view === 'supplier' && (supplier
                ? <><kbd>Enter</kbd> Assign {supplier.supplier_name} <kbd>Delete</kbd> Remove from list <kbd>↕</kbd> Navigate</>
                : <>Pick a supplier to assign · <kbd>↕</kbd> Navigate</>)}
              {view === 'assigned' && <><kbd>↕</kbd> Navigate</>}
              {view === 'review' && <><kbd>↕</kbd> Navigate</>}
            </span>
            <span className="ow-status-sep" aria-hidden="true">•</span>
            <span className="ow-count">{summary.loading ? 'Loading…' : `${activeCount} shown`}</span>
            <button type="button" className="ow-btn ow-btn-sm ow-details-toggle"
              aria-pressed={!owLayout.sideHidden}
              title={owLayout.sideHidden ? 'Show the side detail panel' : 'Hide the side detail panel to widen the grid'}
              onClick={() => setOwLayout((l) => ({ ...l, sideHidden: !l.sideHidden }))}>
              {owLayout.sideHidden ? 'Show details' : 'Hide details'}
            </button>
          </div>
          {selectedCode != null && abnormal.byCode[String(selectedCode)] && (
            <AbnormalSalesStrip
              info={abnormal.byCode[String(selectedCode)]}
              productName={line?.name}
              multipliers={{ abnormal: abnormal.abnormal, warning: abnormal.warning }}
              busy={abnormal.busy}
              readOnly={finalized}
              onToggle={abnormal.toggle}
            />
          )}
          <div className="ow-grid" ref={owGridScrollRef}>
        {view === 'bulkassign' ? (
          <OwBulkAssign
            store={store}
            session={session}
            finalized={finalized}
            reloadKey={reloadTick}
            selectedCode={selectedCode}
            onSelect={setSelectedCode}
            onError={setError}
            onAssigned={(res) => {
              setBanner(`Assigned ${res.assigned} product(s) to ${res.suppliers} supplier(s) by best margin.`);
              setReloadTick((t) => t + 1);
              loadWorkflow();
            }}
          />
        ) : view === 'qty' ? (
          <table className="ow-cfg">
            <colgroup>{owColgroupPct(qtyCols)}</colgroup>
            <thead>
              <tr>{qtyCols.map((c) => <th key={c.key} className={owHeaderClass(c.key, c.align)}>{c.key === 'offer' ? <span className="ow-header-icon">{c.label}</span> : c.key === 'orqty' ? <OwOrQtyHeaderLabel label={c.label} /> : c.label}</th>)}</tr>
              {filtersOpen && <OwFilterRow cols={qtyCols} gridKind="qty" values={columnFilters.qty} onChange={setColFilter} wantedOptions={wantedOptions} />}
            </thead>
            <tbody>
              {filteredQty.map((row, index) => {
                const reviewed = reviewedCodes.has(row.productcode);
                return (
                  <tr key={row.productcode}
                    className={`${selectedCode === row.productcode ? 'ow-row-sel' : ''}${reviewed ? ' ow-row-assigned' : ''}`.trim() || undefined}
                    onClick={() => { setSelectedCode(row.productcode); qtyRowRefs.current[index]?.focus(); }}>
                    {qtyCols.map((c, i) => (
                      <td key={c.key} className={owBodyCellClass(c.key, c.align)}
                        {...(i === 0 ? {
                          tabIndex: -1,
                          ref: (el) => { qtyRowRefs.current[index] = el; },
                          onKeyDown: (e) => {
                            if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
                            e.preventDefault();
                            const dir = e.key === 'ArrowDown' ? 1 : -1;
                            const target = Math.min(Math.max(index + dir, 0), filteredQty.length - 1);
                            if (target !== index) setSelectedCode(filteredQty[target].productcode);
                            // Always re-anchor focus, even at a boundary (target===index) or
                            // onto a disabled target row -- never leave focus stranded where a
                            // later keypress could fall through to the browser's default scroll.
                            owFocusGridRow(qtyRefs, qtyRowRefs, target);
                          }
                        } : {})}>
                        {renderQtyCell(c, row, index, reviewed)}
                      </td>
                    ))}
                  </tr>
                );
              })}
              {!filteredQty.length && <tr><td colSpan={qtyCols.length} className="ow-empty">{loading ? 'Loading…' : error ? 'Could not load this grid — see the error above.' : qtyRows.length ? 'No products match.' : `Every pending product for ${store || 'this store'} has been reviewed.`}</td></tr>}
            </tbody>
          </table>
        ) : view === 'pending' ? (
          <table className="ow-fixed">
            <colgroup>{owColgroupPct(pendingCols)}</colgroup>
            <thead>
              <tr>{pendingCols.map((c) => <th key={c.key} className={owHeaderClass(c.key, c.align)}>{c.key === 'offer' ? <span className="ow-header-icon">{c.label}</span> : c.key === 'orqty' ? <OwOrQtyHeaderLabel label={c.label} /> : c.label}</th>)}</tr>
              {filtersOpen && <OwFilterRow cols={pendingCols} gridKind="pending" values={columnFilters.pending} onChange={setColFilter} wantedOptions={wantedOptions} />}
            </thead>
            <tbody>
              {filteredPending.map((row, index) => (
                <tr key={row.productcode}
                  className={selectedCode === row.productcode ? 'ow-row-sel' : undefined}
                  onClick={() => { setSelectedCode(row.productcode); pendingRowRefs.current[index]?.focus(); }}>
                  {pendingCols.map((c, ci) => (
                    <td key={c.key} className={owBodyCellClass(c.key, c.align)}
                      {...(ci === 0 ? {
                        tabIndex: -1,
                        ref: (el) => { pendingRowRefs.current[index] = el; },
                        onKeyDown: (e) => {
                          if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
                          e.preventDefault();
                          const dir = e.key === 'ArrowDown' ? 1 : -1;
                          const target = Math.min(Math.max(index + dir, 0), filteredPending.length - 1);
                          if (target !== index) setSelectedCode(filteredPending[target].productcode);
                          owFocusGridRow(pendingQtyRefs, pendingRowRefs, target);
                        }
                      } : {})}>
                      {renderPendingCell(c, row, index)}
                    </td>
                  ))}
                </tr>
              ))}
              {!filteredPending.length && <tr><td colSpan={pendingCols.length} className="ow-empty">{loading ? 'Loading…' : error ? 'Could not load this grid — see the error above.' : 'No reviewed products are waiting on a supplier assignment.'}</td></tr>}
            </tbody>
          </table>
        ) : view === 'review' ? (
          <table className="ow-cfg">
            <colgroup>{owColgroupPct(reviewCols)}</colgroup>
            <thead>
              <tr>{reviewCols.map((c) => <th key={c.key} className={owHeaderClass(c.key, c.align)}>{c.key === 'offer' ? <span className="ow-header-icon">{c.label}</span> : c.key === 'orqty' ? <OwOrQtyHeaderLabel label={c.label} /> : c.label}</th>)}</tr>
              {filtersOpen && <OwFilterRow cols={reviewCols} gridKind="review" values={columnFilters.review} onChange={setColFilter} wantedOptions={wantedOptions} />}
            </thead>
            <tbody>
              {filteredRows.map((row, i) => (
                <tr key={row.ProductCode} className={selectedCode === row.ProductCode ? 'ow-row-sel' : undefined}
                  onClick={() => { setSelectedCode(row.ProductCode); reviewRowRefs.current[i]?.focus(); }}>
                  {reviewCols.map((c, ci) => (
                    <td key={c.key} className={owBodyCellClass(c.key, c.align)}
                      {...(ci === 0 ? {
                        tabIndex: -1,
                        ref: (el) => { reviewRowRefs.current[i] = el; },
                        onKeyDown: (e) => {
                          if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
                          e.preventDefault();
                          const dir = e.key === 'ArrowDown' ? 1 : -1;
                          const target = Math.min(Math.max(i + dir, 0), filteredRows.length - 1);
                          if (target !== i) setSelectedCode(filteredRows[target].ProductCode);
                          owFocusGridRow(reviewQtyRefs, reviewRowRefs, target);
                        }
                      } : {})}>
                      {renderReviewCell(c, row, i)}
                    </td>
                  ))}
                </tr>
              ))}
              {!filteredRows.length && <tr><td colSpan={reviewCols.length} className="ow-empty">{loading ? 'Loading…' : error ? 'Could not load this grid — see the error above.' : 'No open order rows for this store.'}</td></tr>}
            </tbody>
          </table>
        ) : view === 'supplier' ? (
          <table className="ow-fixed">
            <colgroup>{owColgroupPct(supplierCols)}</colgroup>
            <thead>
              <tr>{supplierCols.map((c) => <th key={c.key} className={owHeaderClass(c.key, c.align)} title={c.key === 'check' ? 'Already qty-checked' : undefined}>{c.key === 'offer' || c.key === 'check' ? <span className="ow-header-icon">{c.label}</span> : c.key === 'orqty' ? <OwOrQtyHeaderLabel label={c.label} /> : c.label}</th>)}</tr>
              {filtersOpen && <OwFilterRow cols={supplierCols} gridKind="supplier" values={columnFilters.supplier} onChange={setColFilter} wantedOptions={wantedOptions} />}
            </thead>
            <tbody>
              {supplierRowVirtualizer.getVirtualItems().length > 0 && (
                <tr style={{ height: supplierRowVirtualizer.getVirtualItems()[0].start }} aria-hidden="true">
                  <td colSpan={supplierCols.length} style={{ padding: 0, border: 0 }} />
                </tr>
              )}
              {supplierRowVirtualizer.getVirtualItems().map((virtualRow) => {
                const index = virtualRow.index;
                const row = filteredRows[index];
                const isAssigned = statusOf(row) === 1;
                const value = edits[row.ProductCode] ?? row.OrderQty;
                // Same qty-checked state as the Qty Check grid (both read/write
                // OrderManagement.Qtycheck) -- a product reviewed there already
                // shows reviewed here too, instead of looking untouched just
                // because this is a different screen.
                const reviewed = Number(row.Qtycheck) === 1 || qtyCheckedHere.has(row.ProductCode);
                return (
                  <tr key={row.ProductCode}
                    className={`${selectedCode === row.ProductCode ? 'ow-row-sel' : ''}${isAssigned ? ' ow-row-assigned' : ''}${reviewed ? ' ow-row-reviewed' : ''}`.trim() || undefined}
                    onClick={() => { setSelectedCode(row.ProductCode); owFocusGridRow(supplierQtyRefs, supplierRowRefs, index); }}>
                    {supplierCols.map((c, ci) => (
                      <td key={c.key} className={owBodyCellClass(c.key, c.align)}
                        {...(ci === 0 ? {
                          tabIndex: -1,
                          ref: (el) => { supplierRowRefs.current[index] = el; },
                          onKeyDown: (e) => {
                            // Arrow nav when focus is on the row's first cell (an
                            // assigned row's qty box is disabled, so it never gets
                            // focus and lands here instead). The qty box itself
                            // handles its own ArrowUp/Down, so this only ever fires
                            // from the cell, not double-stepping the input's move.
                            if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
                            e.preventDefault();
                            const dir = e.key === 'ArrowDown' ? 1 : -1;
                            const target = Math.min(Math.max(index + dir, 0), filteredRows.length - 1);
                            if (target !== index) setSelectedCode(filteredRows[target].ProductCode);
                            // scrollToIndex mounts the target row within the
                            // virtual window first -- see assignedRowVirtualizer's
                            // scrollToIndex comment -- then owFocusGridRow can
                            // find its ref on the next tick instead of a no-op.
                            supplierRowVirtualizer.scrollToIndex(target, { align: 'auto' });
                            requestAnimationFrame(() => owFocusGridRow(supplierQtyRefs, supplierRowRefs, target));
                          }
                        } : {})}>
                        {renderSupplierCell(c, row, index, isAssigned, reviewed, value)}
                      </td>
                    ))}
                  </tr>
                );
              })}
              {(() => {
                const items = supplierRowVirtualizer.getVirtualItems();
                const bottom = items.length
                  ? supplierRowVirtualizer.getTotalSize() - items[items.length - 1].end
                  : 0;
                return bottom > 0 ? (
                  <tr style={{ height: bottom }} aria-hidden="true">
                    <td colSpan={supplierCols.length} style={{ padding: 0, border: 0 }} />
                  </tr>
                ) : null;
              })()}
              {!filteredRows.length && <tr><td colSpan={supplierCols.length} className="ow-empty">{loading ? 'Loading…' : error ? 'Could not load this grid — see the error above.' : (loadAll ? 'No open orderable products for this store.' : (supplier ? 'No orderable products for this supplier.' : 'Select a supplier above, or “Load all products”.'))}</td></tr>}
            </tbody>
          </table>
        ) : (
          <table className="ow-fixed">
            <colgroup>{owColgroupPct(assignedCols)}</colgroup>
            <thead>
              <tr>{assignedCols.map((c) => <th key={c.key} className={owHeaderClass(c.key, c.align)}>{c.key === 'offer' ? <span className="ow-header-icon">{c.label}</span> : c.label}</th>)}</tr>
              {filtersOpen && <OwFilterRow cols={assignedCols} gridKind="assigned" values={columnFilters.assigned} onChange={setColFilter} wantedOptions={wantedOptions} />}
            </thead>
            <tbody>
              {assignedRowVirtualizer.getVirtualItems().length > 0 && (
                <tr style={{ height: assignedRowVirtualizer.getVirtualItems()[0].start }} aria-hidden="true">
                  <td colSpan={assignedCols.length} style={{ padding: 0, border: 0 }} />
                </tr>
              )}
              {assignedRowVirtualizer.getVirtualItems().map((virtualRow) => {
                const index = virtualRow.index;
                const row = filteredAssigned[index];
                return (
                <tr key={row.ProductCode}
                  className={selectedCode === row.ProductCode ? 'ow-row-sel' : undefined}
                  onClick={() => { setSelectedCode(row.ProductCode); assignedRowRefs.current[index]?.focus(); }}>
                  {assignedCols.map((c, ci) => (
                    <td key={c.key} className={owBodyCellClass(c.key, c.align)}
                      {...(ci === 0 ? {
                        tabIndex: -1,
                        ref: (el) => { assignedRowRefs.current[index] = el; },
                        onKeyDown: (e) => {
                          // Focus the row's first CELL, not the <tr> itself --
                          // a table-row element was an unreliable keydown
                          // target in this app's older Chromium (it could be
                          // .focus()ed and show as document.activeElement,
                          // but didn't reliably deliver keydown, so arrows
                          // silently did nothing once focus landed on a bare
                          // row).
                          if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
                          e.preventDefault();
                          const dir = e.key === 'ArrowDown' ? 1 : -1;
                          const target = Math.min(Math.max(index + dir, 0), filteredAssigned.length - 1);
                          if (target !== index) setSelectedCode(filteredAssigned[target].ProductCode);
                          // Scroll the target into the mounted window FIRST --
                          // with virtualization, a ref outside the current
                          // virtual window is null (not yet rendered), so
                          // immediate focus would silently no-op at a window
                          // boundary. scrollToIndex mounts it synchronously
                          // within the same virtualizer measurement pass; the
                          // ref is then readable on the next tick.
                          assignedRowVirtualizer.scrollToIndex(target, { align: 'auto' });
                          requestAnimationFrame(() => {
                            const el = assignedRowRefs.current[target];
                            if (el) { el.focus(); el.scrollIntoView({ block: 'nearest', inline: 'nearest' }); }
                          });
                        }
                      } : {})}>
                      {renderAssignedCell(c, row, index)}
                    </td>
                  ))}
                </tr>
                );
              })}
              {(() => {
                const items = assignedRowVirtualizer.getVirtualItems();
                const bottom = items.length
                  ? assignedRowVirtualizer.getTotalSize() - items[items.length - 1].end
                  : 0;
                return bottom > 0 ? (
                  <tr style={{ height: bottom }} aria-hidden="true">
                    <td colSpan={assignedCols.length} style={{ padding: 0, border: 0 }} />
                  </tr>
                ) : null;
              })()}
              {!filteredAssigned.length && <tr><td colSpan={assignedCols.length} className="ow-empty">{loading ? 'Loading…' : error ? 'Could not load this grid — see the error above.' : supplier ? 'No products assigned to this supplier yet.' : 'Select a supplier above.'}</td></tr>}
            </tbody>
          </table>
        )}
          </div>
        </div>

        {owBottomPanels.length > 0 && (
          <div className="ow-bottom-dock">{owBottomPanels.map(renderOwPanel)}</div>
        )}
        </div>

        {owSideShown && (
        <aside className="ow-side">
          <OwLineContext
            line={line}
            prices={linePrices}
            note={lineNote}
            collapsed={lineCollapsed}
            onToggleCollapse={() => setLineCollapsed((v) => !v)}
            assignAction={view === 'supplier' && activeLineRow ? (
              <button
                type="button"
                className={`ow-btn ow-btn-sm ${line?.assignment === 'assigned' ? 'ow-btn-danger' : 'ow-btn-primary'}`}
                disabled={!supplier || assigningCode === activeLineRow.ProductCode || finalized}
                onClick={() => toggleAssign(activeLineRow)}
              >
                {assigningCode === activeLineRow.ProductCode ? '…' : (line?.assignment === 'assigned' ? 'Unassign' : 'Assign')}
              </button>
            ) : null}
          />
          <div className="ow-side-panels">{owSidePanels.map(renderOwPanel)}</div>
        </aside>
        )}
      </div>
      {owRecord && (
        <OwDocumentCard
          kind={owRecord.kind}
          store={store}
          row={owRecord.row}
          productCode={owRecord.productCode}
          session={session}
          onClose={() => setOwRecord(null)}
        />
      )}
      {!historyPanelShown && infoCode != null && line && String(line.code) === String(infoCode) && (
        <OwProductInfoCard
          line={line}
          prices={linePrices}
          note={lineNote}
          history={history}
          historyLoading={historyLoading}
          onClose={() => setInfoCode(null)}
        />
      )}

      <div className="ow-footer" role="status">
        <span className="ow-footer-item"><b>Store</b> {store || '—'}</span>
        <span className="ow-status-sep" aria-hidden="true">•</span>
        {orderHeaderError ? (
          <span className="ow-footer-item ow-footer-error">Order info unavailable</span>
        ) : orderHeader === null ? (
          <span className="ow-footer-item">Loading order info…</span>
        ) : orderHeader.order_id == null ? (
          <span className="ow-footer-item">No active order</span>
        ) : (
          <>
            <span className="ow-footer-item"><b>Order</b> #{orderHeader.order_no ?? orderHeader.order_id} ({orderHeader.order_id})</span>
            <span className="ow-footer-item">{fmtOwDateTime(orderHeader.order_datetime)}</span>
            <span className="ow-status-sep" aria-hidden="true">•</span>
            {orderHeader.last_grn ? (
              <>
                <span className="ow-footer-item"><b>Last GRN</b> {orderHeader.last_grn}</span>
                <span className="ow-footer-item">{fmtOwDateTime(orderHeader.last_grn_datetime)}</span>
              </>
            ) : (
              <span className="ow-footer-item">No GRN recorded</span>
            )}
            <span className="ow-status-sep" aria-hidden="true">•</span>
            {orderHeader.last_sale_bill_no ? (
              <>
                <span className="ow-footer-item"><b>Last C Bill</b> {orderHeader.last_sale_bill_no}</span>
                <span className="ow-footer-item">{fmtOwDateTime(orderHeader.last_bill_datetime)}</span>
              </>
            ) : (
              <span className="ow-footer-item">No C bill recorded</span>
            )}
          </>
        )}
      </div>
    </section>
  );
}

// Order Workspace export settings (destination folder, file format, column
// selection, per-supplier split) moved to ./OwExportKit.js -- shared by
// Order Workspace, Procurement (PROCUREMENT_UI.exportKit below), the Label
// Exporter screen and the WhatsApp-share path.
// Calendar day in local time. Today and yesterday are named so a same-week
// GRN or sale is not just another short date.
function owWhen(value) {
  if (!value) return null;
  const raw = String(value).slice(0, 10);
  const parts = raw.split('-');
  if (parts.length !== 3) return { text: raw, when: '' };
  const then = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
  if (Number.isNaN(then.getTime())) return { text: raw, when: '' };
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const diff = Math.round((today.getTime() - then.getTime()) / 86400000);
  const short = `${parts[2]}/${parts[1]}/${parts[0].slice(2)}`;
  const day = `${parts[0]}-${parts[1]}-${parts[2]}`;
  if (diff === 0) return { text: `Today · ${short}`, when: 'today', day };
  if (diff === 1) return { text: `Yesterday · ${short}`, when: 'yesterday', day };
  return { text: short, when: '', day };
}
// Same date part as fmtOwDate, plus HH:MM -- for footer order/GRN timestamps
// where the time matters (date alone can't distinguish same-day reorders).
function fmtOwDateTime(value) {
  if (!value) return '—';
  const str = String(value);
  const datePart = fmtOwDate(str);
  const timeMatch = str.match(/(\d{2}):(\d{2})(?::\d{2})?/);
  return timeMatch ? `${datePart} ${timeMatch[1]}:${timeMatch[2]}` : datePart;
}
// Days elapsed since a date (LR/LS Date -> LR/LS Days), whole days, floor.
function fmtOwDaysAgo(value) {
  if (!value) return '—';
  const then = new Date(String(value).slice(0, 10));
  if (Number.isNaN(then.getTime())) return '—';
  const days = Math.floor((Date.now() - then.getTime()) / 86400000);
  return days < 0 ? '—' : String(days);
}
// Whole-number-only quantity input: no decimals, empty clears to 0.
function owWholeQty(raw) {
  const n = Math.trunc(Number(raw));
  // 0 stays valid: Backspace / "don't want" commits a zero. Positive entries
  // are whole packs and stop at five digits.
  if (!Number.isFinite(n) || n < 0) return 0;
  return Math.min(n, 99999);
}
// True when a Backspace keypress has nothing left to delete -- the field is
// already empty, or the whole value is selected (so this keystroke would
// clear it entirely rather than remove one digit). Lets Backspace double as
// the "Don't Want to Order" shortcut without breaking ordinary digit-by-digit
// editing.
function owIsClearKeypress(e) {
  const el = e.target;
  return el.value === '' || (el.selectionStart === 0 && el.selectionEnd === String(el.value).length);
}
// Product names come out of the legacy DB with inconsistent padding --
// leading/trailing spaces and doubled-up internal spaces -- which makes a
// dense product list look ragged and hard to scan. Display-only cleanup,
// never sent back to the server.
function owCleanName(name) {
  return String(name ?? '').replace(/\s+/g, ' ').trim();
}

const OW_QTYCHECK_WORD = { checked: 'Checked', pending: 'Pending', unknown: 'Unknown' };

// Selected-line context for the Order Workspace side column. Shows only the
// fields on `line`. It does not approve a quantity or apply a recommendation.
function owFact(label, value, tone) {
  if (value == null || value === '') return null;
  return { label, value, tone };
}

function OwLineFacts({ line, prices, note }) {
  const pricesMatch = prices && String(prices.code) === String(line.code) ? prices : null;
  const qtyFacts = [
    owFact('Original', line.originalQty == null ? null : fmtOwQty(line.originalQty)),
    owFact('Final', line.finalQty == null ? null : fmtOwQty(line.finalQty), owQtyDiffTone(line.originalQty, line.finalQty) || undefined),
    owFact('Stock', line.stock == null ? null : fmtOwQty(line.stock), Number(line.stock) === 0 ? 'zero' : undefined),
    owFact('90d sales', line.salesQty == null ? null : fmtOwQty(line.salesQty), 'sales'),
    owFact('Max', line.maxQty == null ? null : fmtOwQty(line.maxQty)),
    owFact('Supplier stock', line.supplierStock == null ? null : fmtOwQty(line.supplierStock)),
  ].filter(Boolean);
  const priceFacts = [
    owFact('Cost', pricesMatch ? fmtOwMoney(pricesMatch.cost) : '—'),
    owFact('PTR', pricesMatch ? fmtOwMoney(pricesMatch.ptr) : '—'),
    owFact('MRP', line.mrp == null ? (pricesMatch ? fmtOwMoney(pricesMatch.purchaseMrp) : '—') : fmtOwMoney(line.mrp)),
    owFact('Discount', pricesMatch && pricesMatch.discount != null && pricesMatch.discount !== '' ? fmtOwPct(pricesMatch.discount) : '—'),
    owFact('Received', pricesMatch ? fmtOwQty(pricesMatch.receivedQty) : '—'),
    owFact('Free', pricesMatch ? fmtOwQty(pricesMatch.freeQty) : '—'),
  ].filter(Boolean);
  const status = [
    line.qtyCheck ? (OW_QTYCHECK_WORD[line.qtyCheck] || line.qtyCheck) : null,
    line.offer ? 'Offer' : null,
    line.assignment === 'assigned' ? 'Assigned' : (line.assignment === 'open' ? 'Open' : null),
    line.wanted || null,
    line.finalQty === 0 ? 'Not ordering' : null,
  ].filter(Boolean);
  const saleDate = line.lastSaleDate || pricesMatch?.lastSaleDate || null;
  const grnDate = pricesMatch?.grnDate || null;
  const received = line.lastReceivedDate || null;
  const saleWhen = owWhen(saleDate);
  const grnWhen = owWhen(grnDate);
  const receivedWhen = owWhen(received);
  const sameReceipt = Boolean(grnWhen?.day && receivedWhen?.day && grnWhen.day === receivedWhen.day);
  const movement = [];
  if (saleWhen) movement.push({ key: 'sale', label: 'Last sale', when: saleWhen });
  if (grnWhen) movement.push({ key: 'grn', label: 'Last GRN', when: grnWhen });
  if (receivedWhen && !sameReceipt) movement.push({ key: 'received', label: 'Last received', when: receivedWhen });
  if (pricesMatch?.supplier) movement.push({ key: 'supplier', text: pricesMatch.supplier });
  return (
    <>
      {status.length > 0 && <p className="ow-line-status">{status.join(' · ')}</p>}
      <div className="ow-line-split">
        {qtyFacts.length > 0 && (
          <dl className="ow-facts">
            {qtyFacts.map((fact) => (
              <div key={fact.label} className={fact.tone === 'sales' ? 'is-sales' : undefined}>
                <dt>{fact.label}</dt>
                <dd className={fact.tone === 'zero' ? 'is-zero' : fact.tone === 'up' || fact.tone === 'down' ? `is-${fact.tone}` : undefined}>
                  {fact.value}
                  {(fact.tone === 'up' || fact.tone === 'down') && fact.label === 'Final' && (
                    <OwQtyDiffArrow from={line.originalQty} to={line.finalQty} />
                  )}
                </dd>
              </div>
            ))}
          </dl>
        )}
        <dl className="ow-facts ow-facts-price">
          {priceFacts.map((fact) => (
            <div key={fact.label}><dt>{fact.label}</dt><dd>{fact.value}</dd></div>
          ))}
        </dl>
      </div>
      {movement.length > 0 && (
        <p className="ow-line-meta ow-line-move">
          {movement.map((bit) => (bit.when ? (
            <span key={bit.key} className={`ow-move ow-move-${bit.key}`}>{bit.label} <b className={bit.when.when ? `ow-when ow-when-${bit.when.when}` : undefined}>{bit.when.text}</b></span>
          ) : (
            <span key={bit.key}>{bit.text}</span>
          )))}
        </p>
      )}
      {line.supplierName && <p className="ow-line-meta">Order supplier {line.supplierName}</p>}
      {line.remarks && <p className="ow-line-meta">Remarks {line.remarks}</p>}
      {note && <p className="ow-line-note">{note}</p>}
    </>
  );
}

function OwLineContext({ line, prices, note, collapsed, onToggleCollapse, assignAction }) {
  if (!line) {
    return (
      <div className="ow-line">
        <div className="ow-line-empty">Select a product. Stock, quantities, cost, PTR, and MRP show here.</div>
      </div>
    );
  }
  return (
    <section className={`ow-line${Number(line.stock) === 0 ? ' is-nostock' : ''}`} aria-label="Selected product">
      <div className="ow-line-top">
        <div className="ow-line-id">
          <strong className="ow-line-name" title={line.name}>{line.name}</strong>
          <span className="ow-line-sub">
            {line.code != null && <span>#{line.code}</span>}
            {line.unit && <span>{line.unit}</span>}
            {line.pack != null && <span>Pack {fmtOwQty(line.pack)}</span>}
          </span>
        </div>
        <button type="button" className="ow-btn ow-btn-sm ow-line-toggle" aria-expanded={!collapsed} onClick={onToggleCollapse}>
          {collapsed ? 'Show' : 'Hide'}
        </button>
      </div>
      {!collapsed && (
        <>
          <OwLineFacts line={line} prices={prices} note={note} />
          {assignAction}
        </>
      )}
    </section>
  );
}

function OwProductInfoCard({ line, prices, note, history, historyLoading, onClose }) {
  useEffect(() => {
    function closeOnEscape(event) {
      if (event.key !== 'Escape') return;
      event.stopPropagation();
      event.preventDefault();
      onClose();
    }
    window.addEventListener('keydown', closeOnEscape, true);
    return () => window.removeEventListener('keydown', closeOnEscape, true);
  }, [onClose]);
  const rows = Array.isArray(history) ? history.slice(0, 25) : [];
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="purchase-detail-card ow-doc-card ow-product-info" role="dialog" aria-modal="true" aria-labelledby="ow-product-info-title" onClick={(e) => e.stopPropagation()}>
        <div className="purchase-detail-header">
          <div className="purchase-detail-heading">
            <div>
              <span className="purchase-detail-eyebrow">#{line.code ?? '—'}{line.unit ? ` · ${line.unit}` : ''}{line.pack != null ? ` · Pack ${fmtOwQty(line.pack)}` : ''}</span>
              <strong id="ow-product-info-title" title={line.name}>{line.name}</strong>
            </div>
          </div>
          <button type="button" className="purchase-detail-close" onClick={onClose} aria-label="Close">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m7.4 6 4.6 4.6L16.6 6 18 7.4 13.4 12l4.6 4.6-1.4 1.4-4.6-4.6L7.4 18 6 16.6l4.6-4.6L6 7.4 7.4 6Z" /></svg>
          </button>
        </div>
        <div className="purchase-detail-body">
          <OwLineFacts line={line} prices={prices} note={note} />
          <div className="ow-panel-title">Previous orders{rows.length > 0 && <span className="ow-panel-count">Last {rows.length}</span>}</div>
          <div className="ow-doc-lines">
            <table className="ow-intel-table">
              <thead><tr><th className="ow-num">Or Qty</th><th className="ow-num">Org Order</th><th className="ow-num">Pack</th><th className="ow-num">MRP</th><th>Remarks</th><th>Wanted Date</th><th>Wanted</th><th>Or Supplier</th></tr></thead>
              <tbody>
                {rows.map((row, i) => (
                  <tr key={i}><td className="ow-num">{fmtOwQty(row.Orqty)}</td><td className="ow-num">{fmtOwQty(row.OrgOrderQty)}</td><td className="ow-num">{fmtOwQty(row.saleunit)}</td><td className="ow-num">{fmtOwMoney(row.MRP)}</td><td>{row.remarks ?? '—'}</td><td>{fmtOwDate(row.Wanteddate)}</td><td>{row.WantedType ?? '—'}</td><td>{row.Orsupplier ?? '—'}</td></tr>
                ))}
                {!rows.length && <tr><td colSpan={8} className="ow-empty">{historyLoading ? 'Loading previous orders…' : 'No previous orders for this product.'}</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
// Shared row-navigation for every Order Workspace product grid (Qty Review,
// Review All, By Supplier): ArrowUp/ArrowDown must never step the OR QTY
// value the way a native <input type="number"> would -- they move focus to
// the previous/next VISIBLE row's qty input instead, scrolling the grid (not
// the page) to reveal it if needed. Each grid keeps its own Enter/Escape
// semantics; this is the one place the arrow-key logic lives so it isn't
// duplicated (and drifted) across the three call sites.
function owFocusRow(refs, index) {
  const el = refs.current[index];
  if (!el || el.disabled) return; // out of range / disabled -- stay put
  el.focus();
  el.scrollIntoView({ block: 'nearest', inline: 'nearest' });
}
// Navigation lands on a row's qty box when it's editable, but a disabled box
// (mid-save, an already-assigned row, a finalized order) must never strand
// focus there with nothing happening -- that left the keyboard in limbo and a
// LATER keypress could fall through to the browser's own default scroll
// (what read as "arrow keys just scroll"). Fall back to the row's FIRST CELL
// instead (not the <tr> itself: a table-row element is an unreliable keydown
// target in this app's older Chromium -- <tr tabIndex> could be .focus()ed
// and show as document.activeElement, but didn't reliably deliver keydown).
// Used by every grid's row-level keydown handler, not just By Supplier.
function owFocusGridRow(qtyRefs, rowRefs, index) {
  const input = qtyRefs?.current?.[index];
  if (input && !input.disabled) {
    input.focus();
    input.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    return true;
  }
  const cell = rowRefs?.current?.[index];
  if (cell) {
    cell.focus();
    cell.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    return true;
  }
  return false;
}
function owHandleRowArrowKeys(e, refs, index) {
  if (e.key === 'ArrowDown') { e.preventDefault(); owFocusRow(refs, index + 1); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); owFocusRow(refs, index - 1); }
}

// Qty Check edit indicator: ONE arrow matching the direction of change plus
// the signed delta (▲ +5 / ▼ -3) -- green for an increase, red for a
// decrease, a flat dash (no arrow) for no change. `from` is the row's
// originally-loaded orderqty, `to` is whatever's currently showing (edited
// or not).
// One comparison for the quantity and its arrow: above the original is up
// and green, below it is down and red. Zero is not a color by itself.
function owQtyDiffTone(from, to) {
  if (from == null || from === '' || to == null || to === '') return '';
  const diff = Number(to) - Number(from);
  if (!Number.isFinite(diff) || diff === 0) return '';
  return diff > 0 ? 'up' : 'down';
}
function OwQtyDiffArrow({ from, to }) {
  const tone = owQtyDiffTone(from, to);
  if (!tone) return <span className="ow-qty-diff ow-qty-diff-flat" aria-label="unchanged">—</span>;
  const up = tone === 'up';
  const diff = Number(to) - Number(from);
  return (
    <span className={`ow-qty-diff ow-qty-diff-${tone}`} aria-label={`${up ? 'increased' : 'decreased'} by ${Math.abs(diff)}`}>
      {up ? '▲' : '▼'} {fmtOwSigned(diff)}
    </span>
  );
}
