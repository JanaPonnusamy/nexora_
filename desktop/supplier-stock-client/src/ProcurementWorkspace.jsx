import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { api } from './api/client.js';
import { AbnormalMark, AbnormalSalesStrip, useAbnormalSales } from './abnormalSales.jsx';
import { PW_DOCKS, PW_PANEL_DEFS, pwAssignRefusal, pwColumnOrder, pwCompareSuppliers, pwColumnWidth, pwExportGuard, pwFinalizePlan, pwGrnForSelection, pwKey, pwNormalizePanels, pwOfferRemark, pwOfferText, pwQtyKeyAction, pwSupplierLine, pwWholeQty } from './procurementWorkspaceView.js';
import { SuggestionPanel, invalidateProductSuggestions, useProductSuggestions } from './suggestionPanel.jsx';
import { StoreTrendsPanel } from './storeTrends.jsx';
import { SupplierCompareBadge, SupplierCompareCard, useSupplierCompare } from './supplierCompare.jsx';
import WebPanel from './webPanel.jsx';
import { SiteCheckBar, SiteMark, useSiteCheck } from './siteCheckBar.jsx';
import { MatchReview, fmtDur, useHarvest, useMatchReview } from './harvestReview.jsx';
import { OwBulkAssign } from './bulkAssign.jsx';
import { roEnter, siteAvailable, siteCheckOne, siteKind, siteScript } from './siteCheck.js';
import { WhatsAppSendDialog, storeWhatsAppAvailable } from './storeWhatsApp.jsx';
import { SupplierWhatsAppDialog, useSupplierWhatsApp } from './supplierWhatsApp.jsx';

// Monthly Trend: look back 6 calendar months, draw the latest 4 that have
// data, or 5 when the detail column is wide enough.
const PW_TREND_FIT = { fetch: 6, min: 4, max: 5 };

// Procurement -- ONE workspace (owner ruling 2026-10-25): the Order
// Workspace's model (legacy OrderNMC order via /api/legacy-order, its
// processes Qty Check -> Pending Order / Rejected -> By Supplier -> Supplier
// Orders -> Export, its keys and Finalize) in the UniNex Purchase Manager
// design: process tabs, product grid | Supplier Recommendation cards | product
// detail column, totals footer. The old Order Workspace stays untouched.
//
// Supplier cards come from the platform recommendation (store + product code,
// suggestionPanel.jsx); a card's real supplier code is resolved to the
// store's legacy UnifiedSupplierCODE before it is assigned.
//
// Order Workspace building blocks (detail panels, record card, export card,
// supplier picker, export file helpers) come in through `ui`, so this file
// never imports App.jsx back.

const PW_PROCESSES = [
  { key: 'qty', label: 'Qty Check', view: 'qty' },
  // Abnormal = the Qty Check rows (same loader, same Or Qty keys) limited to
  // products with a 5x abnormal bill still to review.
  { key: 'abnormal', label: 'Abnormal', view: 'qty', abnormal: true },
  { key: 'pending', label: 'Pending Order', view: 'pending', scope: 'order' },
  { key: 'rejected', label: 'Rejected', view: 'pending', scope: 'rejected' },
  { key: 'supplier', label: 'By Supplier', view: 'supplier' },
  { key: 'assigned', label: 'Supplier Orders', view: 'assigned' },
];
// Website (owner 2026-11-04): the open, unassigned products checked one by one
// on the supplier's own site in the Sites panel (siteCheckBar.jsx).
const PW_SUPPLIER_MODES = [['history', 'History'], ['stock', 'Live Stock'], ['all', 'All products'], ['site', 'Website']];
const PW_PRODUCT_TYPES = ['All', 'Pharma', 'Non Pharma'];
const PW_STATE_LABEL = { pending: 'Not Reviewed', checked: 'Reviewed', rejected: 'Rejected', assigned: 'Assigned', closed: 'Closed' };
const PW_DETAIL_TABS = [['summary', 'Summary'], ['history', 'History'], ['decisions', 'Decisions']];
// Skip modes -- the platform's skipModes.ts codes (backend repository.
// SKIP_MODES). The two "Until next" skips carry into later orders until the
// product sells again; Current Order is this order only.
const PW_SKIP_MODES = [['current_refresh', 'Current Order'], ['until_next_sales', 'Until Next Sales'], ['until_next_demand', 'Until Next Demand']];
const PW_SKIP_MODE_KEY = 'nexora.desktop.pwSkipMode';

// Grid columns. #, Product, Or Qty and State are always shown; the rest are
// toggled in ⚙ and also hide themselves when no row of the list carries the
// field (each process returns a different shape).
const PW_COLUMNS = [
  { key: 'sno', label: 'S.No', width: 56, align: 'right', fixed: true },
  { key: 'name', label: 'Product', fixed: true },
  { key: 'offer', label: '🎁', width: 34, align: 'center', title: 'Free-qty offer in purchase history' },
  // Same positions as the Order Workspace grid: QCheck/state, Or Qty, Stock,
  // Pack, Desc, Sls Qty, MRP, LRD, LSD, Max Qty, Wanted, then supplier extras.
  { key: 'state', label: 'State', fixed: true },
  { key: 'qty', label: 'Or Qty', width: 88, align: 'right', fixed: true },
  // Export remark, next to the final qty (owner 2026-11-04): fills with the
  // offer the qty matches ("9+1"), or the operator types a short note
  // ("12%"). Export file only -- never saved to the order.
  { key: 'xremark', label: 'Remark', menu: 'Export remark', width: 64,
    title: 'Export remark: goes into the order export only, not saved to the order. Fills with the offer the qty matches (9+1); type up to 10 characters (12%, 9+1)' },
  { key: 'stock', label: 'Stock', width: 52, align: 'right' },
  // The picked supplier's live stock + its offer sit right after Stock
  // (owner 2026-11-04), so both are read together with the store's stock.
  { key: 'sstock', label: 'S.Stock', width: 58, align: 'right', title: "Supplier's own live stock" },
  { key: 'soffer', label: 'S.Offer', width: 56, align: 'right', title: "Supplier's live offer for this product (sch + free)" },
  { key: 'pack', label: 'Pack', width: 44, align: 'right' },
  { key: 'unit', label: 'Unit', width: 56 },
  { key: 'sls', label: 'Sls Qty', width: 54, align: 'right', title: 'Sales qty in the order window' },
  { key: 'mrp', label: 'MRP', width: 62, align: 'right' },
  { key: 'lrd', label: 'LPD', width: 40, align: 'right', title: 'Days since last purchase (received)' },
  { key: 'lsd', label: 'LSD', width: 40, align: 'right', title: 'Days since last sale' },
  { key: 'maxqty', label: 'Max Qty', width: 58, align: 'right', title: 'Largest single sale' },
  // Wider than the old 88px clip ("Regular Or...") without pushing the grid
  // into a horizontal scrollbar at 1366. A saved width still wins. The cell
  // title carries the full value when it does not fit.
  { key: 'wanted', label: 'Wanted', width: 116 },
  { key: 'disc', label: 'Disc', width: 46, align: 'right' },
  { key: 'minqty', label: 'Min Qty', width: 58, align: 'right' },
  { key: 'rack', label: 'Rack', width: 60 },
  { key: 'remarks', label: 'Remarks', menu: 'Order remarks', width: 130 },
  // Optional extras (off by default; ticked in ⚙ settings).
  { key: 'code', label: 'Code', width: 64, align: 'right', title: 'Product code' },
  { key: 'org', label: 'Org Qty', width: 60, align: 'right', title: 'Original order qty from the order process' },
  { key: 'diff', label: 'Diff', width: 54, align: 'right', title: 'Or Qty minus Org Qty' },
  { key: 'type', label: 'Type', width: 76, title: 'Pharma / Non Pharma' },
  { key: 'offerpat', label: 'Last Offer', width: 64, align: 'right', title: 'Last free-qty offer seen in purchases (base + free)' },
  { key: 'lrddate', label: 'Last GRN', width: 68, align: 'right', title: 'Last received date' },
  { key: 'lsddate', label: 'Last Sale', width: 68, align: 'right', title: 'Last sale date' },
  // Last column: the assigned supplier (owner ruling) -- it shows itself as
  // soon as any listed row is assigned (empty columns hide).
  { key: 'supplier', label: 'Supplier', width: 150 },
];
// sno + name always lead; every other column can be moved in ⚙ settings.
const PW_LEAD_KEYS = ['sno', 'name'];
const PW_MOVABLE_KEYS = PW_COLUMNS.map((c) => c.key).filter((k) => !PW_LEAD_KEYS.includes(k));
const PW_OPTIONAL_COLUMNS = PW_COLUMNS.filter((c) => !c.fixed);
// Wanted is optional (off by default, owner ruling) -- enable it in ⚙.
const PW_DEFAULT_COLUMNS = ['xremark', 'offer', 'pack', 'stock', 'sstock', 'soffer', 'sls', 'lsd', 'lrd', 'mrp', 'disc', 'minqty', 'rack', 'supplier'];
// Shown on an empty list (nothing to probe for data yet).
const PW_EMPTY_LIST_COLUMNS = new Set(['xremark', 'offer', 'pack', 'unit', 'stock', 'sls', 'lsd', 'lrd', 'mrp', 'maxqty', 'wanted']);
const PW_ROW_HEIGHT = { compact: 28, normal: 32, large: 38 };
// Export remarks: short notes only (owner: 8-10 characters, no essays).
const PW_NOTE_MAX = 10;
const PW_NOTES_PREFIX = 'nexora.desktop.pwExportRemarks::';
// Product (the one flexible column) never shrinks below this; past it the
// grid scrolls sideways inside its own box instead of hiding the name.
const PW_PRODUCT_MIN = 100;

const PW_STATUS_STYLES = [['tick', 'Tick'], ['text', 'Text']];
const PW_GEAR_PATH = 'M19.14 12.94c.04-.3.06-.61.06-.94s-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.49.49 0 0 0-.59-.22l-2.39.96a7 7 0 0 0-1.62-.94l-.36-2.54a.48.48 0 0 0-.48-.41h-3.84a.47.47 0 0 0-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96a.48.48 0 0 0-.59.22L2.74 8.87a.47.47 0 0 0 .12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58a.49.49 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32a.47.47 0 0 0-.12-.61l-2.01-1.58ZM12 15.6a3.6 3.6 0 1 1 0-7.2 3.6 3.6 0 0 1 0 7.2Z';
const PW_EXPORT_KEY_MAP = {
  productCode: 'product_code', productName: 'product_name', orderQty: 'order_qty',
  saleUnit: 'sale_unit', mrp: 'mrp', discount: 'discount', category: 'category',
  subLocation: 'sub_location', rack: 'rack',
};

// One row shape for every process. Qty Check / Pending rows come lowercase,
// By Supplier / Supplier Orders rows PascalCase (the legacy queries' own
// shapes); `raw` keeps the original for anything not mapped here.
function pwNorm(view, r) {
  if (view === 'qty' || view === 'pending') {
    return {
      raw: r, code: r.productcode, key: pwKey(r.productcode), name: r.productname,
      qty: r.orderqty, org: r.orgorderqty ?? r.orderqty,
      stock: r.totalstock, pack: r.saleunit, unit: r.unitdescription, sls: r.slsqty, mrp: r.mrp,
      lrd: r.lastreceiveddate, lsd: r.lastsaledate, maxqty: r.maxsaleqty, wanted: r.wantedtype,
      offer: Boolean(r.IsOffer), type: r.producttypename, remarks: r.remarks ?? null,
      qtycheck: view === 'pending' ? 1 : 0, status: 0, supplier: null, skipReason: r.SkipReason ?? null,
    };
  }
  return {
    raw: r, code: r.ProductCode, key: pwKey(r.ProductCode), name: r.ProductName,
    qty: r.OrderQty, org: r.OrgOrderQty ?? r.OrderQty,
    stock: r.TotalStock, pack: r.SaleUnit, unit: r.UnitDescription, sls: r.SLSQty, mrp: r.MRP,
    lrd: r.LastReceivedDate ?? r.lastreceiveddate, lsd: r.LastSaleDate ?? r.lastsaledate,
    maxqty: r.MaxSaleQty ?? r.maxsaleqty, wanted: r.WantedType, offer: Boolean(r.IsOffer), type: r.ProductTypeName,
    qtycheck: r.Qtycheck == null ? null : Number(r.Qtycheck),
    status: view === 'assigned' ? 1 : (Number(r.Status) || 0),
    supplier: r.OrSupplier ?? null, sstock: r.S_Stock, sch: r.Sch, free: r.Free, disc: r.Discount, minqty: r.MinQty, rack: r.Rack,
    remarks: r.Remarks ?? null, skipReason: r.SkipReason ?? null,
  };
}

// Status 1 = assigned to a supplier, 2 = closed by Compare; otherwise the
// Qty Check result (server Qtycheck or reviewed in this session) with qty 0
// meaning "don't order" (Rejected).
function pwState(row, reviewedHere) {
  if (row.status === 1) return 'assigned';
  if (row.status === 2) return 'closed';
  if (!(row.qtycheck === 1 || reviewedHere)) return 'pending';
  return Number(row.qty) > 0 ? 'checked' : 'rejected';
}

function pwQty(value) {
  if (value === null || value === undefined || value === '') return '—';
  const n = Number(value);
  return Number.isFinite(n) ? n.toLocaleString(undefined, { maximumFractionDigits: 2 }) : '—';
}
function pwMoney(value) {
  if (value === null || value === undefined || value === '') return '—';
  const n = Number(value);
  return Number.isFinite(n) ? n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—';
}
function pwRupees(value) {
  const text = pwMoney(value);
  return text === '—' ? text : `₹${text}`;
}
function pwDate(value) {
  if (!value) return '—';
  const parts = String(value).slice(0, 10).split('-');
  return parts.length === 3 ? `${parts[2]}/${parts[1]}/${parts[0].slice(2)}` : String(value);
}
function pwDateTime(value) {
  if (!value) return '';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '';
  return `${pwDate(value)} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}
// Whole days since a date (LSD / LPD).
function pwDaysAgo(value) {
  if (!value) return '—';
  const then = new Date(String(value).slice(0, 10));
  if (Number.isNaN(then.getTime())) return '—';
  const days = Math.floor((Date.now() - then.getTime()) / 86400000);
  return days < 0 ? '—' : String(days);
}
function pwCleanName(name) {
  return String(name ?? '').replace(/\s+/g, ' ').trim();
}
// Backspace with nothing left to delete doubles as "don't order".
function pwIsClearKeypress(e) {
  const el = e.target;
  return el.value === '' || (el.selectionStart === 0 && el.selectionEnd === String(el.value).length);
}
function pwLoad(key, fallback) {
  try { const v = localStorage.getItem(key); return v == null ? fallback : JSON.parse(v); } catch { return fallback; }
}
function pwSave(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* best effort */ }
}
function pwAsArray(value) {
  return Array.isArray(value) ? value : Array.isArray(value?.items) ? value.items : [];
}
function pwHasValue(row, key) {
  if (key === 'offer') return row.offer;
  if (key === 'code') return Boolean(row.key);
  if (key === 'diff') return row.org != null;
  if (key === 'lrddate') return Boolean(row.lrd);
  if (key === 'lsddate') return Boolean(row.lsd);
  if (key === 'offerpat') return Number(row.raw?.LastOfferFreeQty) > 0;
  const v = row[key];
  return v !== null && v !== undefined && v !== '';
}

// Row height / weight follow the operator's Order Workspace layout settings.
function pwReadLayout() {
  const saved = pwLoad('nexora.desktop.owLayout', {}) || {};
  return {
    rowSize: ['compact', 'normal', 'large'].includes(saved.rowSize) ? saved.rowSize : 'normal',
    rowWeight: saved.rowWeight === 'bold' ? 'bold' : 'normal',
  };
}

function PwIcon({ path }) {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d={path} /></svg>;
}

function PwQtyDiff({ from, to }) {
  const diff = Number(to) - Number(from);
  if (!Number.isFinite(diff) || diff === 0) return null;
  const up = diff > 0;
  const body = Math.abs(diff).toLocaleString(undefined, { maximumFractionDigits: 2 });
  return (
    <span className={`ow-qty-diff ${up ? 'ow-qty-diff-up' : 'ow-qty-diff-down'}`} title={`Original ${pwQty(from)} (${up ? '+' : '-'}${body})`}>
      {up ? '▲' : '▼'}{body}
    </span>
  );
}

export default function ProcurementWorkspace({ session, settings, hidden, ui }) {
  const { IntelPanel, DocumentCard, ExportCard, SupplierPicker, exportKit } = ui;

  // ---- store: legacy order DB name (NMC, NMW...) = platform store_code ----
  const [stores, setStores] = useState([]);
  const [store, setStore] = useState(() => {
    try { return localStorage.getItem('nexora.desktop.pwLegacyStore') || ''; } catch { return ''; }
  });
  const [platformStores, setPlatformStores] = useState([]);
  const [suppliers, setSuppliers] = useState([]);

  // ---- process / data ----
  const [processKey, setProcessKey] = useState('qty');
  const process = PW_PROCESSES.find((p) => p.key === processKey) || PW_PROCESSES[0];
  const view = process.view;
  const [supplierMode, setSupplierMode] = useState('history');
  const [supplier, setSupplier] = useState(null);
  const siteMode = view === 'supplier' && supplierMode === 'site';
  // "Check in site" on History / Live Stock / All products: the same website
  // check over that view's rows, without switching to the Website view.
  const [siteCheckOn, setSiteCheckOn] = useState(false);
  useEffect(() => { setSiteCheckOn(false); }, [supplierMode, supplier?.supplier_code, store]);
  const siteChecking = siteMode || (view === 'supplier' && siteCheckOn);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [banner, setBanner] = useState('');
  const [workflow, setWorkflow] = useState(null);
  const [orderHeader, setOrderHeader] = useState(null);
  const [reloadTick, setReloadTick] = useState(0);

  // ---- working set (cleared on every reload) ----
  const [edits, setEdits] = useState({});
  const [reviewedHere, setReviewedHere] = useState(() => new Set());
  const [stickyKeys, setStickyKeys] = useState(() => new Set());
  const [removedKeys, setRemovedKeys] = useState(() => new Set());
  const [savingKey, setSavingKey] = useState(null);
  const [assigningKey, setAssigningKey] = useState(null);
  const [selectedKey, setSelectedKey] = useState(null);

  // ---- filters ----
  const [search, setSearch] = useState('');
  const [productType, setProductType] = useState('All');
  const [wantedFilter, setWantedFilter] = useState('All');

  // ---- layout / settings ----
  const [layout, setLayout] = useState(pwReadLayout);
  const [skipMode, setSkipMode] = useState(() => {
    const saved = pwLoad(PW_SKIP_MODE_KEY, 'current_refresh');
    return PW_SKIP_MODES.some(([code]) => code === saved) ? saved : 'current_refresh';
  });
  useEffect(() => { pwSave(PW_SKIP_MODE_KEY, skipMode); }, [skipMode]);
  const [statusStyle, setStatusStyle] = useState(() => (pwLoad('nexora.desktop.pwStatusStyle2', 'tick') === 'text' ? 'text' : 'tick'));
  const [shownCols, setShownCols] = useState(() => {
    const saved = pwLoad('nexora.desktop.pwLegacyColumns4', null);
    return Array.isArray(saved) ? saved.filter((k) => PW_OPTIONAL_COLUMNS.some((c) => c.key === k)) : PW_DEFAULT_COLUMNS;
  });
  // Column position + width overrides (⚙ settings), saved per PC like the
  // Order Workspace grids. Keys missing from an older save keep their
  // default slot.
  const [colOrder, setColOrder] = useState(() => pwColumnOrder(pwLoad('nexora.desktop.pwColumnOrder4', null), PW_MOVABLE_KEYS));
  const [colWidths, setColWidths] = useState(() => {
    const saved = pwLoad('nexora.desktop.pwColumnWidths', null);
    return saved && typeof saved === 'object' && !Array.isArray(saved) ? saved : {};
  });
  const [detailHidden, setDetailHidden] = useState(() => pwLoad('nexora.desktop.pwDetailHidden', false) === true);
  // 🌐 Sites: the supplier portals take the right-hand columns (owner 2026-11-04).
  const [webOn, setWebOn] = useState(() => pwLoad('nexora.desktop.pwWebPanel', false) === true);
  // ⚡ Auto Assign: one-click, assign the whole reviewed order to the best
  // supplier by purchase history (bulkAssign.jsx / legacyAutoAssign) -- no
  // website, no per-supplier screen switching.
  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkSel, setBulkSel] = useState(null);
  // Auto Assign gate: confirm live stock on the supplier's own site before
  // assigning (for suppliers that have a web order portal).
  const [assignCheckStock, setAssignCheckStock] = useState(() => pwLoad('nexora.desktop.pwAssignCheckStock', true) !== false);
  // Supplier stock compare card under the current row (By Supplier /
  // Supplier Orders); on by default, ⚙ turns it off per PC.
  const [compareOn, setCompareOn] = useState(() => pwLoad('nexora.desktop.pwCompareCard', true) !== false);
  // The other-supplier stock card under the current row, switched separately
  // from the compare badges (Settings: "Show other-supplier stock card").
  const [compareCardOn, setCompareCardOn] = useState(() => pwLoad('nexora.desktop.pwCompareCardShow', true) !== false);
  // Detail panels: show/hide, dock (middle/side/bottom) and order, saved per PC.
  const [panels, setPanels] = useState(() => pwNormalizePanels(pwLoad('nexora.desktop.pwPanels', null)));
  const setPanel = (key, patch) => setPanels((cur) => cur.map((p) => (p.key === key ? { ...p, ...patch } : p)));
  const movePanel = (index, dir) => setPanels((cur) => {
    const j = index + dir;
    if (j < 0 || j >= cur.length) return cur;
    const next = [...cur];
    [next[index], next[j]] = [next[j], next[index]];
    return next;
  });
  const [settingsOpen, setSettingsOpen] = useState(false);
  const settingsRef = useRef(null);
  const [record, setRecord] = useState(null);
  const [decisions, setDecisions] = useState({ loading: false, rows: [] });
  // Latest GRN of the product the detail panels last loaded (OrderIntelligence
  // onLatest: cost, PTR, MRP, discount, received, free, supplier, dates).
  const [latestGrn, setLatestGrn] = useState(null);
  const onLatestPurchase = useCallback((info) => {
    setLatestGrn((cur) => (cur && info && JSON.stringify(cur) === JSON.stringify(info) ? cur : info));
  }, []);

  // ---- export ----
  const [exportSettings, setExportSettings] = useState(exportKit.defaults);
  const [exportOpen, setExportOpen] = useState(false);
  const [splitCount, setSplitCount] = useState(0);
  const [exporting, setExporting] = useState(false);
  const [removingUnavailable, setRemovingUnavailable] = useState(false);
  const [lastExport, setLastExport] = useState(null);
  const [waSendOpen, setWaSendOpen] = useState(false);
  const [waContactOpen, setWaContactOpen] = useState(false);
  const exportBtnRef = useRef(null);

  const gridRef = useRef(null);
  const qtyRefs = useRef([]);
  const rowRefs = useRef([]);

  useEffect(() => { if (!hidden) setLayout(pwReadLayout()); }, [hidden]);
  useEffect(() => { pwSave('nexora.desktop.pwStatusStyle2', statusStyle); }, [statusStyle]);
  useEffect(() => { pwSave('nexora.desktop.pwLegacyColumns4', shownCols); }, [shownCols]);
  useEffect(() => { pwSave('nexora.desktop.pwColumnOrder4', colOrder); }, [colOrder]);
  useEffect(() => { pwSave('nexora.desktop.pwColumnWidths', colWidths); }, [colWidths]);
  useEffect(() => { pwSave('nexora.desktop.pwDetailHidden', detailHidden); }, [detailHidden]);
  useEffect(() => { pwSave('nexora.desktop.pwWebPanel', webOn); }, [webOn]);
  useEffect(() => { pwSave('nexora.desktop.pwAssignCheckStock', assignCheckStock); }, [assignCheckStock]);
  useEffect(() => { pwSave('nexora.desktop.pwCompareCard', compareOn); }, [compareOn]);
  useEffect(() => { pwSave('nexora.desktop.pwCompareCardShow', compareCardOn); }, [compareCardOn]);
  useEffect(() => { pwSave('nexora.desktop.pwPanels', panels); }, [panels]);
  useEffect(() => { if (store) { try { localStorage.setItem('nexora.desktop.pwLegacyStore', store); } catch { /* best effort */ } } }, [store]);
  useEffect(() => {
    exportKit.read().then((loaded) => {
      if (loaded._migratedSupplierWiseOff || loaded._migratedFileFormatXls) exportKit.write(loaded);
      setExportSettings(loaded);
    });
  }, [exportKit]);
  const updateExportSettings = (patch) => setExportSettings((cur) => {
    const next = { ...cur, ...patch };
    exportKit.write(next);
    return next;
  });
  useEffect(() => {
    if (!settingsOpen) return undefined;
    const onDown = (e) => { if (!settingsRef.current?.contains(e.target)) setSettingsOpen(false); };
    const onKey = (e) => { if (e.key === 'Escape') { e.stopPropagation(); setSettingsOpen(false); } };
    document.addEventListener('mousedown', onDown);
    window.addEventListener('keydown', onKey, true);
    return () => { document.removeEventListener('mousedown', onDown); window.removeEventListener('keydown', onKey, true); };
  }, [settingsOpen]);

  // ---- stores ----
  useEffect(() => {
    api.legacyStores(session)
      .then((list) => {
        const arr = pwAsArray(list);
        setStores(arr);
        setStore((cur) => (cur && arr.some((s) => s.store_name === cur) ? cur : (arr[0]?.store_name || '')));
      })
      .catch((e) => setError(e.message));
    api.listStores(session).then((list) => setPlatformStores(pwAsArray(list))).catch(() => setPlatformStores([]));
  }, [session]);
  const platformStore = platformStores.find((s) => String(s.store_code || '').toUpperCase() === String(store).toUpperCase()) || null;
  const tenantId = platformStore?.tenant_id || settings?.tenantId || session?.user?.tenant_id || '';

  // The store's legacy supplier list: the By Supplier picker AND the card ->
  // UnifiedSupplierCODE resolution.
  useEffect(() => {
    setSuppliers([]); setSupplier(null);
    if (!store) return undefined;
    let cancelled = false;
    api.legacySuppliers(store, '', session)
      .then((r) => { if (!cancelled) setSuppliers(pwAsArray(r)); })
      .catch(() => { if (!cancelled) setSuppliers([]); });
    return () => { cancelled = true; };
  }, [store, session]);

  const loadWorkflow = useCallback(() => {
    if (!store) return;
    api.legacyOrderWorkflow(store, session).then(setWorkflow).catch((e) => setError(e.message));
  }, [store, session]);
  useEffect(() => { setWorkflow(null); setOrderHeader(null); }, [store]);
  useEffect(() => { loadWorkflow(); }, [loadWorkflow]);
  useEffect(() => {
    if (!store) return undefined;
    let cancelled = false;
    api.legacyOrderHeader(store, session)
      .then((r) => { if (!cancelled) setOrderHeader(r); })
      .catch(() => { if (!cancelled) setOrderHeader({ error: true }); });
    return () => { cancelled = true; };
  }, [store, session, reloadTick]);

  // Back on this screen after time elsewhere: reload if the order moved
  // (regenerated or edited elsewhere) -- same fingerprint as Order Workspace.
  const wasHidden = useRef(hidden);
  const leftFingerprint = useRef(null);
  useEffect(() => {
    if (hidden) {
      if (orderHeader?.order_id != null) leftFingerprint.current = `${orderHeader.order_id}|${orderHeader.updated_at ?? ''}`;
    } else if (wasHidden.current && store) {
      api.legacyOrderHeader(store, session).then((fresh) => {
        if (fresh.order_id == null) return;
        const fp = `${fresh.order_id}|${fresh.updated_at ?? ''}`;
        if (leftFingerprint.current !== null && leftFingerprint.current !== fp) {
          setBanner('Order data changed elsewhere — the latest order has been loaded.');
          setReloadTick((t) => t + 1);
        }
        setOrderHeader(fresh);
      }).catch(() => {});
    }
    wasHidden.current = hidden;
  }, [hidden, store, session]); // eslint-disable-line react-hooks/exhaustive-deps

  // While this screen is open: a new order generated elsewhere (Order
  // Process on the web page) must replace the grid. The hidden->shown check
  // above never fires if the operator stays on this screen, which left a
  // fresh NMS order unseen (2026-10-26). Checks every minute and when the
  // app window regains focus.
  const orderIdRef = useRef(null);
  useEffect(() => { orderIdRef.current = orderHeader?.order_id ?? null; }, [orderHeader]);
  useEffect(() => {
    if (hidden || !store) return undefined;
    let cancelled = false;
    const check = () => {
      api.legacyOrderHeader(store, session).then((fresh) => {
        if (cancelled || fresh?.order_id == null) return;
        if (orderIdRef.current != null && String(fresh.order_id) !== String(orderIdRef.current)) {
          setBanner(`New order #${fresh.order_no ?? fresh.order_id} (${fresh.order_id}) generated — loaded.`);
          setReloadTick((t) => t + 1);
          loadWorkflow();
        }
        setOrderHeader(fresh);
      }).catch(() => {});
    };
    const timer = setInterval(check, 60000);
    window.addEventListener('focus', check);
    return () => { cancelled = true; clearInterval(timer); window.removeEventListener('focus', check); };
  }, [hidden, store, session, loadWorkflow]);

  // ---- grid data for the active process ----
  useEffect(() => {
    if (!store) return undefined;
    let cancelled = false;
    setLoading(true); setError(''); setRows([]); setEdits({}); setSelectedKey(null);
    setReviewedHere(new Set()); setStickyKeys(new Set()); setRemovedKeys(new Set());
    let req;
    if (view === 'qty') req = api.legacyQtyCheckRows(store, session);
    else if (view === 'pending') req = api.legacyPendingOrderRows(store, session);
    else if (view === 'supplier') {
      if (supplierMode === 'all' || supplierMode === 'site') req = api.legacyAllOpenOrders(store, session);
      else if (supplier) req = api.legacyOrdersBySupplier(store, supplier.supplier_code, supplierMode, session);
    } else if (supplier) req = api.legacyAssignedOrders(store, supplier.supplier_code, session);
    if (!req) { setLoading(false); return undefined; }
    req
      .then((r) => { if (!cancelled) setRows(pwAsArray(r).map((row) => pwNorm(view, row))); })
      .catch((e) => { if (!cancelled) setError(e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [store, view, supplier, supplierMode, session, reloadTick]);
  useEffect(() => { setExportOpen(false); }, [processKey]);

  const finalized = workflow?.status === 'FINALIZED';
  // Supplier-wise WhatsApp: saved targets + auto-send while assigning.
  const supplierWa = useSupplierWhatsApp({
    store, session, exportKit, exportSettings,
    columnsFor: () => exportKit.columnDefs.filter((c) => c.required || exportSettings.columns[c.key]).map((c) => PW_EXPORT_KEY_MAP[c.key]),
    remarksFor: () => exportRemarks(),
    orderNo: workflow?.order_no != null ? String(workflow.order_no) : workflow?.order_id != null ? String(workflow.order_id) : '',
    onBanner: setBanner, onError: setError,
  });
  const supplierContact = supplier ? supplierWa.contacts[String(supplier.supplier_code)] : null;

  // ---- abnormal sales (open order's products); first load opens on them ----
  // Reloads only for a new order or the ⟳ button -- not on every export /
  // assign tick: the server read is heavy and overlapping copies starved the
  // export itself (2026-11-02).
  const [abnTick, setAbnTick] = useState(0);
  const abnormal = useAbnormalSales({
    enabled: Boolean(store) && orderHeader != null,
    key: `${store}|${orderHeader?.order_id ?? ''}|${abnTick}`,
    load: () => api.legacyAbnormalSales(store, session),
    save: (productCode, bill, value) => api.legacySetDontConsider(store, {
      product_code: String(productCode), bill_no: bill.bill_no, bill_date: bill.bill_date, dont_consider: value,
    }, session),
  });
  // Products whose bills were marked in THIS session keep their strip and stay
  // listed (so a mark can be undone); on the next load a product whose every
  // flagged bill is "don't consider" (level 'reviewed') is not shown again.
  const [abnTouched, setAbnTouched] = useState(() => new Set());
  useEffect(() => { setAbnTouched(new Set()); }, [store, reloadTick]);
  const toggleAbnormal = useCallback((productCode, bill, value) => {
    setAbnTouched((cur) => new Set(cur).add(pwKey(productCode)));
    return abnormal.toggle(productCode, bill, value);
  }, [abnormal.toggle]); // eslint-disable-line react-hooks/exhaustive-deps
  const abnInfo = (key) => {
    const info = abnormal.byCode[key];
    return info && (info.level !== 'reviewed' || abnTouched.has(key)) ? info : null;
  };
  // The Qty Check "Abnormal sales" list: 5x-rule products only (3x warnings
  // show their bills when the row is reviewed).
  const abnormalKeys = useMemo(() => new Set(abnormal.items.filter((i) => i.level === 'abnormal').map((i) => pwKey(i.product_code))), [abnormal.items]);
  // A new store starts on Qty Check. Abnormal opens only when the operator
  // clicks its tab (the tab count still shows how many are waiting).
  useEffect(() => { setProcessKey((k) => (k === 'abnormal' ? 'qty' : k)); }, [store]);
  const pickProcess = setProcessKey;
  const abnormalView = Boolean(process.abnormal);

  // ---- filtering ----
  const term = search.trim().toLowerCase();
  const visible = useMemo(() => rows.filter((r) => {
    if (removedKeys.has(r.key)) return false;
    const sticky = stickyKeys.has(r.key);
    if (process.scope === 'order' && !(Number(r.qty) > 0) && !sticky) return false;
    if (process.scope === 'rejected' && Number(r.qty) > 0 && !sticky) return false;
    if (abnormalView && !abnormalKeys.has(r.key) && !abnTouched.has(r.key) && !sticky) return false;
    if (siteMode && !(r.status === 0 && Number(r.qty) > 0) && !sticky) return false;
    if (term && !pwCleanName(r.name).toLowerCase().includes(term) && !r.key.includes(term)) return false;
    if (productType !== 'All' && r.type !== productType) return false;
    if (wantedFilter !== 'All' && (r.wanted ?? '—') !== wantedFilter) return false;
    return true;
  }), [rows, removedKeys, stickyKeys, process.scope, abnormalView, abnormalKeys, abnTouched, siteMode, term, productType, wantedFilter]);
  const wantedOptions = useMemo(() => [...new Set(rows.map((r) => r.wanted ?? '—'))].sort(), [rows]);
  useEffect(() => { if (wantedFilter !== 'All' && !wantedOptions.includes(wantedFilter)) setWantedFilter('All'); }, [wantedOptions, wantedFilter]);

  // ---- supplier live stock: S.Stock / S.Offer columns, compare card ----
  // Loaded for every view (one cheap call per store): S.Stock / S.Offer fill
  // in History / All products / Supplier Orders, not only Live Stock, and the
  // offer remark reads in-stock suppliers' offers in Qty Check / Pending.
  // The ⚙ compare setting only gates the badge + card.
  const supplierView = view === 'supplier' || view === 'assigned';
  const compare = useSupplierCompare({ store, enabled: true, reloadKey: reloadTick, session });
  const currentCodes = useMemo(() => (supplier ? String(supplier.supplier_code).split(',').map((c) => c.trim()).filter(Boolean) : []), [supplier]);
  // The picked supplier's stock + offer for a row: Live Stock rows carry
  // their own SupplierStock line; other views look it up. null = the
  // supplier does not list the product (no stock).
  const supplierStock = useCallback((row) => {
    if (row.sstock != null) return { stock: row.sstock, sch: row.sch, free: row.free, offer: pwOfferText(row.sch, row.free) };
    const line = supplierView ? pwSupplierLine(compare.byCode[row.key], currentCodes) : null;
    return line ? { stock: line.stock, sch: line.sch, free: line.free, offer: pwOfferText(line.sch, line.free) } : null;
  }, [supplierView, compare.byCode, currentCodes]);
  // The export remark box stays on even while every remark is empty.
  const hasValue = (r, key) => (key === 'xremark' ? true : key === 'sstock' ? supplierStock(r) != null
    : key === 'soffer' ? Boolean(supplierStock(r)?.offer) : pwHasValue(r, key));

  const columns = useMemo(() => [...PW_LEAD_KEYS, ...colOrder].map((k) => PW_COLUMNS.find((c) => c.key === k)).filter((c) => {
    if (!c) return false;
    if (c.fixed) return true;
    if (!shownCols.includes(c.key)) return false;
    return rows.length ? rows.some((r) => hasValue(r, c.key)) : PW_EMPTY_LIST_COLUMNS.has(c.key);
  }).map((c) => {
    // State holds the action buttons, so its width stays computed here.
    // A bare tick/dash (Qty Check, Pending) needs no more than the header.
    if (c.key === 'state') return { ...c, width: (view === 'supplier' || view === 'assigned') && supplier ? 188 : process.scope === 'rejected' ? 160 : statusStyle === 'text' ? 136 : 52 };
    return { ...c, width: pwColumnWidth(c.width, colWidths[c.key]) };
  }),
  [shownCols, colOrder, colWidths, rows, view, statusStyle, supplier, process.scope, supplierStock]);
  // The grid column is only as wide as its columns need: Product is sized to
  // the longest name in the list (190-320px), so on a wide screen the spare
  // width goes to the panels instead of an empty Product column. Narrow
  // screens shrink the grid first (it scrolls sideways past PW_PRODUCT_MIN).
  const gridWidth = useMemo(() => {
    let longest = 0;
    for (const r of rows) longest = Math.max(longest, String(r.name || '').length);
    const nameWidth = Math.min(320, Math.max(190, Math.round(longest * 7.4) + 30));
    return columns.reduce((t, c) => t + (c.width || 0), 0) + nameWidth + 18;
  }, [rows, columns]);
  const moveCol = (key, dir) => setColOrder((cur) => {
    const i = cur.indexOf(key);
    const j = i + dir;
    if (i < 0 || j < 0 || j >= cur.length) return cur;
    const next = [...cur];
    [next[i], next[j]] = [next[j], next[i]];
    return next;
  });
  const resetColumns = () => { setShownCols(PW_DEFAULT_COLUMNS); setColOrder(pwColumnOrder(null, PW_MOVABLE_KEYS)); setColWidths({}); };

  // Keep a valid selection: first visible row once the grid lands.
  useEffect(() => {
    if (loading) return;
    if (!visible.some((r) => r.key === selectedKey)) setSelectedKey(visible[0]?.key ?? null);
  }, [visible, loading, selectedKey]);
  const selectedIndex = visible.findIndex((r) => r.key === selectedKey);
  const selected = selectedIndex >= 0 ? visible[selectedIndex] : (rows.find((r) => r.key === selectedKey) || null);

  // ---- supplier stock compare (card under the current row) ----
  const compareLines = selected && supplierView && compareOn && compareCardOn ? compare.byCode[selected.key] : null;
  const selectedSup = selected ? supplierStock(selected) : null;
  // Any live-stock line at all: a lone current-supplier line still gets the
  // slim "no other supplier has stock -- place here" card.
  const cardKey = compareLines?.length && selectedIndex >= 0 ? selected.key : null;

  // ---- virtualized grid ----
  // Sizes are cached per product, and the carded row under its own key: when
  // the card moves on, the row falls back to its plain measured height. Keyed
  // by index, a row kept its row+card size after the card left (its <tr> never
  // resized, so it was never re-measured) -- every product walked past grew to
  // ~170px in the model and the grid stopped rendering rows mid-screen.
  const getItemKey = useCallback((i) => {
    const key = visible[i]?.key ?? i;
    return key === cardKey ? `${key}|card` : key;
  }, [visible, cardKey]);
  const virt = useVirtualizer({
    count: visible.length,
    getScrollElement: () => gridRef.current,
    estimateSize: () => PW_ROW_HEIGHT[layout.rowSize] || 32,
    getItemKey,
    overscan: 14,
  });
  // The card is a second <tr> under the row: the row's virtual size becomes
  // row + card (the row skips measureElement while it carries the card), so
  // the rows below keep their real offsets.
  const cardIndexRef = useRef(-1);
  cardIndexRef.current = cardKey ? selectedIndex : -1;
  const cardObserver = useRef(null);
  const cardRowRef = useCallback((el) => {
    cardObserver.current?.disconnect();
    cardObserver.current = null;
    if (!el) return;
    const measure = () => {
      const tr = el.previousElementSibling;
      const i = cardIndexRef.current;
      if (i >= 0 && tr && el.isConnected) virt.resizeItem(i, tr.offsetHeight + el.offsetHeight);
    };
    cardObserver.current = new ResizeObserver(measure);
    cardObserver.current.observe(el);
    measure();
  }, [virt]);

  // The abnormal-sales note above the grid shrinks the grid's viewport when
  // it appears/changes; re-scroll so the current row never ends up hidden
  // below it. Retried once after the virtualizer has re-measured the box.
  const abnStripKey = selected && abnInfo(selected.key) ? `${selected.key}|${abnormalView}` : '';
  useEffect(() => {
    if (!abnStripKey || selectedIndex < 0) return undefined;
    const timers = [0, 150].map((ms) => setTimeout(() => revealRow(selectedIndex), ms));
    return () => timers.forEach(clearTimeout);
  }, [abnStripKey]); // eslint-disable-line react-hooks/exhaustive-deps

  // Keep row i on screen, VB.NET style (dgvMain_RowEnter sets
  // FirstDisplayedScrollingRowIndex every 20 rows): when the current row
  // runs past the bottom of the grid, it becomes the TOP row (page jump);
  // moving above the top brings it back to the top. Done by hand on the
  // real row -- the virtualizer's scrollToIndex ignores the sticky header
  // and the horizontal scrollbar, and its delayed re-scroll used to override
  // our correction and leave the current row hidden below the grid.
  // Returns false when the row isn't rendered yet.
  function revealRow(i) {
    const box = gridRef.current;
    const tr = rowRefs.current[i]?.parentElement;
    if (!box || !tr) return false;
    const head = box.querySelector('thead')?.offsetHeight || 0;
    const top = tr.offsetTop;
    // The compare card under the row counts as part of it.
    const card = tr.nextElementSibling?.classList.contains('pw-cmp-tr') ? tr.nextElementSibling.offsetHeight : 0;
    const bottom = top + tr.offsetHeight + card;
    if (bottom > box.scrollTop + box.clientHeight || top < box.scrollTop + head) {
      box.scrollTop = Math.max(0, top - head);
    }
    return true;
  }

  function focusRow(index) {
    if (!visible.length) return;
    const i = Math.min(Math.max(index, 0), visible.length - 1);
    setSelectedKey(visible[i].key);
    // A far jump (row not rendered yet): let the virtualizer bring it in,
    // then the attempt below pins it with revealRow.
    if (!rowRefs.current[i]?.isConnected) virt.scrollToIndex(i, { align: 'start' });
    const attempt = (left) => requestAnimationFrame(() => {
      const input = qtyRefs.current[i];
      const el = input && !input.disabled ? input : rowRefs.current[i];
      if (el && el.isConnected) {
        el.focus({ preventScroll: true });
        revealRow(i);
      } else if (left > 0) attempt(left - 1);
    });
    attempt(6);
  }

  // Land on row 0 once a grid finishes loading (VB FocusOrderQtyCell), unless
  // the operator is already somewhere else on the page.
  useEffect(() => {
    if (loading || hidden || !visible.length) return undefined;
    const frame = requestAnimationFrame(() => {
      const active = document.activeElement;
      if (!active || active === document.body) focusRow(0);
    });
    return () => cancelAnimationFrame(frame);
  }, [loading, view]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---- row mutations ----
  const patchRow = (key, patch) => setRows((cur) => cur.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  const dropEdit = (key) => setEdits((cur) => { const n = { ...cur }; delete n[key]; return n; });
  const addTo = (setter, key) => setter((cur) => new Set(cur).add(key));
  const valueOf = (row) => pwWholeQty(edits[row.key] ?? row.qty);

  // ---- Website check (By Supplier -> Website) ----
  // The supplier's site in the Sites panel; its HO portal list comes up from
  // the panel so the bar can name the linked site.
  const webRef = useRef(null);
  // The selected supplier's own web-order portal (fed by the WebPanel, which
  // reads it from the supplier's OrderSuppliers row). null = no site set.
  const [sitePortal, setSitePortal] = useState(null);
  const site = useSiteCheck({
    webRef, rows: siteChecking ? visible : [], siteUrl: sitePortal?.url || '', supplierName: supplier ? pwCleanName(supplier.supplier_name) : '', qtyOf: valueOf, nameOf: (r) => pwCleanName(r.name),
    resetKey: `${store}|${supplier?.supplier_code || ''}|${siteChecking}|${orderHeader?.order_id ?? ''}`,
    // The product being checked is the current row (no focus taken).
    onStep: (row) => {
      const i = visible.findIndex((r) => r.key === row.key);
      if (i < 0) return;
      setSelectedKey(row.key);
      if (rowRefs.current[i]?.isConnected) revealRow(i); else virt.scrollToIndex(i, { align: 'center' });
    },
  });
  useEffect(() => { if (siteChecking) setWebOn(true); }, [siteChecking]);
  // Checking on the site always shows the supplier's own portal, not
  // whichever tab the panel was last on.
  useEffect(() => {
    if (!siteChecking || !sitePortal?.url) return undefined;
    const t = setTimeout(() => {
      const web = webRef.current;
      if (!web) return;
      const host = (u) => { try { return new URL(u).host; } catch { return ''; } };
      if (host(web.url()) !== host(sitePortal.url)) web.openUrl(sitePortal.url);
    }, 300);
    return () => clearTimeout(t);
  }, [siteChecking, sitePortal?.url]);
  // Harvest the supplier's catalog -> SupplierStock (then Live Stock shows it).
  // orderAt = today's order's generation time (order_id is YYYYMMDDHHMMSS), so
  // the hook auto-harvests a supplier whose stock is older than this order.
  const orderAt = useMemo(() => {
    const id = String(orderHeader?.order_id ?? '');
    const m = id.match(/^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})$/);
    return m ? `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}` : null;
  }, [orderHeader]);
  const harvestHook = useHarvest({ webRef, store, supplierCode: supplier?.supplier_code || '', session, orderAt });
  // The separate "Map supplier products" review (fuzzy-confirm / manual map).
  const matchReview = useMatchReview({ store, supplierCode: supplier?.supplier_code || '', session });
  const [showMapReview, setShowMapReview] = useState(false);
  const [siteAssigning, setSiteAssigning] = useState(false);
  // Confirm: assign every In-cart / Available product to the supplier, one by one (the
  // same assign as Enter); stops at the first failure.
  async function confirmSiteOrder() {
    const picks = visible.filter((r) => ['cart', 'available'].includes(site.marks[r.key]?.state) && r.status === 0);
    if (!supplier || !picks.length) return false;
    setSiteAssigning(true);
    let done = 0;
    try {
      for (const row of picks) {
        const res = await toggleAssign(row);
        if (res?.status !== 1) break;
        done += 1;
      }
    } finally {
      setSiteAssigning(false);
    }
    setBanner(`Website order: assigned ${done} of ${picks.length} product(s) to ${supplier.supplier_name}.`);
    return done === picks.length;
  }

  // ⚡ Auto Assign with the live-stock gate (owner 2026-11-05): history picks
  // each product's supplier (the proposals); then, for any supplier that has
  // a web order portal, the product is confirmed IN STOCK on that supplier's
  // own site before it is assigned. Suppliers with no portal are assigned by
  // history as-is (no site to check). Read-only on the sites -- it searches
  // and reads stock, never adds to a cart or places an order.
  async function assignWithStockCheck(pickedRows) {
    const sleep = (ms) => new Promise((r) => { setTimeout(r, ms); });
    const groups = new Map();           // supplier_code -> { portal, name, items }
    const historyOnly = [];             // supplier has no portal site
    // Each supplier's web-order site comes from its own OrderSuppliers row.
    const portalCache = new Map();
    for (const r of pickedRows) {
      let portal = portalCache.get(r.supplier_code);
      if (portal === undefined) {
        try { portal = (await api.legacySupplierPortal(store, r.supplier_code, session))?.portal || null; }
        catch { portal = null; }
        portalCache.set(r.supplier_code, portal);
      }
      if (!portal || !portal.url) { historyOnly.push(r); continue; }
      const g = groups.get(r.supplier_code) || { portal, name: pwCleanName(r.supplier_name), items: [] };
      g.items.push(r);
      groups.set(r.supplier_code, g);
    }
    const toAssign = historyOnly.map((r) => r.product_code);
    const report = { history: historyOnly.length, confirmed: 0, out: 0, unchecked: 0 };
    if (groups.size) {
      setWebOn(true);                   // the site runs in the web panel
      for (let t = 0; t < 40 && !webRef.current?.ready(); t += 1) await sleep(250);
    }
    for (const [, g] of groups) {
      const web = webRef.current;
      if (!web?.ready()) { report.unchecked += g.items.length; continue; }
      setBanner(`Auto Assign · opening ${g.name}…`);
      web.openUrl(g.portal.url);
      // Wait for a searchable page: RetailOrders lands on its distributor
      // list after login, so enter the distributor; other sites are ready
      // once loaded (auto sign-in runs in the main process).
      let ready = false;
      for (let t = 0; t < 60; t += 1) {
        await sleep(400);
        if (web.loading()) continue;
        const u = web.url();
        if (siteKind(u) === 'retailorders') {
          if (/prodadd/.test(u)) { ready = true; break; }
          if (/nav\/distributors/.test(u)) await web.exec(siteScript(roEnter, g.name)).catch(() => {});
        } else { ready = true; break; }
      }
      if (!ready) { report.unchecked += g.items.length; continue; }
      let avail = 0;
      for (let i = 0; i < g.items.length; i += 1) {
        const r = g.items[i];
        setBanner(`Auto Assign · ${g.name}: checking stock ${i + 1}/${g.items.length} — ${pwCleanName(r.product_name)}…`);
        let res = null;
        try { res = await siteCheckOne(web, pwCleanName(r.product_name), Number(r.order_qty) || 0); } catch { res = null; }
        if (res && res.state === 'blocked') { report.unchecked += 1; continue; }
        if (res && siteAvailable(res.state)) { toAssign.push(r.product_code); avail += 1; } else { report.out += 1; }
      }
      report.confirmed += avail;
    }
    const res = toAssign.length ? await api.legacyAutoAssign(store, toAssign, session) : { assigned_count: 0 };
    const parts = [`${report.history} by history`, `${report.confirmed} confirmed in stock`];
    const tail = [report.out ? `${report.out} out of stock` : '', report.unchecked ? `${report.unchecked} not checked` : ''].filter(Boolean).join(', ');
    return {
      assigned_count: res.assigned_count ?? toAssign.length,
      message: `Auto-assigned ${res.assigned_count ?? toAssign.length} (${parts.join(', ')})${tail ? ` — ${tail}, left open` : ''}.`,
    };
  }

  // ---- export remarks (owner 2026-11-04) ----
  // A short note per product that goes into the order export only -- never
  // saved to OrderNMC (its Remarks already carries the order's own notes).
  // Untyped, it shows the offer the final qty matches (9+1 -> 9, 18, 27...):
  // the picked supplier's live offer, else (no supplier picked) an in-stock
  // supplier's, else the last purchase-history offer. Typed notes ("12%",
  // "9+1") win, and are kept on this PC for the current order only; '' =
  // cleared on purpose (no auto offer either).
  const notesKey = store && orderHeader?.order_id != null ? `${PW_NOTES_PREFIX}${store}::${orderHeader.order_id}` : '';
  const [notesState, setNotesState] = useState({ key: '', map: {} });
  useEffect(() => {
    if (!notesKey) return;
    try {
      // Notes of this store's earlier orders are done with.
      Object.keys(localStorage)
        .filter((k) => k.startsWith(`${PW_NOTES_PREFIX}${store}::`) && k !== notesKey)
        .forEach((k) => localStorage.removeItem(k));
    } catch { /* storage unavailable: notes just live for this session */ }
    const saved = pwLoad(notesKey, {});
    setNotesState({ key: notesKey, map: saved && typeof saved === 'object' && !Array.isArray(saved) ? saved : {} });
  }, [notesKey, store]);
  useEffect(() => { if (notesState.key) pwSave(notesState.key, notesState.map); }, [notesState]);
  const typedNotes = notesState.key === notesKey ? notesState.map : {};
  const isTyped = (key) => Object.prototype.hasOwnProperty.call(typedNotes, key);
  const setNote = (key, text) => setNotesState((cur) => (cur.key === notesKey
    ? { ...cur, map: { ...cur.map, [key]: String(text).slice(0, PW_NOTE_MAX) } } : cur));
  const resetNote = (key) => setNotesState((cur) => {
    if (cur.key !== notesKey || !Object.prototype.hasOwnProperty.call(cur.map, key)) return cur;
    const map = { ...cur.map };
    delete map[key];
    return { ...cur, map };
  });
  function liveOffers(row) {
    const sup = supplierStock(row);
    if (sup) return [sup];
    return supplier ? [] : pwCompareSuppliers(compare.byCode[row.key], []).ranked.filter((l) => l.inStock);
  }
  const offerNote = (row) => pwOfferRemark(valueOf(row), [
    ...liveOffers(row),
    { sch: row.raw?.LastOfferBaseQty, free: row.raw?.LastOfferFreeQty, reduce: true },
  ]);
  const noteOf = (row) => (isTyped(row.key) ? typedNotes[row.key] : offerNote(row));
  // {product_code: remark} sent with an export: every typed note plus each
  // loaded row's note; the server keeps only the exported products.
  function exportRemarks() {
    const out = Object.fromEntries(Object.entries(typedNotes).map(([k, t]) => [k, String(t).trim()]).filter(([, t]) => t));
    rows.forEach((r) => { const t = String(noteOf(r) || '').trim(); if (t) out[r.key] = t; });
    return out;
  }
  function onNoteKey(e, row, index) {
    if (e.key === 'Enter') focusRow(index);
    else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') focusRow(index + (e.key === 'ArrowDown' ? 1 : -1));
    else if (e.key === 'Escape') { resetNote(row.key); focusRow(index); }
    else return;
    e.preventDefault();
    e.stopPropagation();
  }

  // Qty Check commit (OrderManagement Qtycheck=1 + the qty), then optionally
  // move. Focus moves first; the save runs behind it (slow remote links).
  async function commitReviewed(row, value, nextIndex) {
    if (!store || finalized || row.status === 1) { if (nextIndex != null) focusRow(nextIndex); return false; }
    if (nextIndex != null) focusRow(nextIndex);
    setSavingKey(row.key);
    try {
      await api.legacyUpdateQtyCheck(store, row.code, value, session);
      patchRow(row.key, { qty: value, qtycheck: 1 });
      addTo(setReviewedHere, row.key);
      addTo(setStickyKeys, row.key);
      dropEdit(row.key);
      return true;
    } catch (e) {
      setError(e.message);
      return false;
    } finally {
      setSavingKey(null);
      loadWorkflow();
    }
  }

  // Esc / the Rejected mode picker: skip with a platform skip mode (server
  // sets Or Qty 0 + reviewed and, for "Until next", carries it forward).
  async function skipRow(row, mode, nextIndex) {
    if (!store || finalized || row.status === 1) { if (nextIndex != null) focusRow(nextIndex); return false; }
    if (nextIndex != null) focusRow(nextIndex);
    setSavingKey(row.key);
    try {
      await api.legacySkipProduct(store, row.code, mode, session);
      patchRow(row.key, { qty: 0, qtycheck: 1, skipReason: mode });
      addTo(setReviewedHere, row.key);
      addTo(setStickyKeys, row.key);
      dropEdit(row.key);
      return true;
    } catch (e) {
      setError(e.message);
      return false;
    } finally {
      setSavingKey(null);
      loadWorkflow();
    }
  }

  // Assign / unassign with the toolbar supplier (status 0 <-> 1 toggle).
  async function toggleAssign(row, sup = supplier) {
    if (!store || !sup || finalized) return null;
    setAssigningKey(row.key); setBanner('');
    try {
      const edited = edits[row.key];
      if (edited != null && Number(edited) !== Number(row.qty)) {
        await api.legacyUpdateOrderQty(store, row.code, Number(edited), session);
        patchRow(row.key, { qty: Number(edited) });
        dropEdit(row.key);
      }
      const res = await api.legacyAssignSupplier(store, row.code, sup.supplier_code, sup.supplier_name, session);
      if (view === 'assigned' && res.status !== 1) setRows((cur) => cur.filter((r) => r.key !== row.key));
      else patchRow(row.key, { status: res.status, supplier: res.status === 1 ? sup.supplier_name : null, qtycheck: 1 });
      addTo(setStickyKeys, row.key);
      setBanner(res.status === 1
        ? `Assigned ${pwCleanName(row.name)} → ${sup.supplier_name} (qty ${pwQty(res.order_qty)}).`
        : `Cleared supplier from ${pwCleanName(row.name)}.`);
      if (res.status === 1) supplierWa.onAssigned(sup.supplier_code);
      return res;
    } catch (e) {
      setError(e.message);
      return null;
    } finally {
      setAssigningKey(null);
      loadWorkflow();
    }
  }

  // Delete key / ✕: drop the row from THIS list only (no DB write) -- it stays
  // open for another supplier, like VB's dgvMain.Rows.Remove.
  function removeFromList(row, index) {
    addTo(setRemovedKeys, row.key);
    requestAnimationFrame(() => focusRow(index));
  }

  // ---- Supplier Recommendation cards ----
  const suggestions = useProductSuggestions({
    tenantId, storeId: platformStore?.store_id || '', productCode: selected ? selected.key : null, session,
  });
  const [zone, setZone] = useState('qty');
  const [supCursor, setSupCursor] = useState(0);
  const [cardBusy, setCardBusy] = useState(false);
  const suggestRef = useRef(null);
  useEffect(() => { setZone('qty'); setSupCursor(0); setLatestGrn(null); }, [selectedKey, store]);
  useEffect(() => { invalidateProductSuggestions(); }, [reloadTick]);

  // A card's real supplier code -> the store's legacy UnifiedSupplierCODE
  // (which can join several branch codes, "107,108,109"); same-name entry
  // first when one code sits in more than one unified group.
  const legacySupplierFor = useCallback((card) => {
    const code = String(card?.supplier_code ?? '');
    const matches = suppliers.filter((s) => String(s.supplier_code).split(',').map((x) => x.trim()).includes(code));
    if (!matches.length) return null;
    const name = pwCleanName(card.supplier_name).toUpperCase();
    return matches.find((s) => pwCleanName(s.supplier_name).toUpperCase() === name) || matches[0];
  }, [suppliers]);
  const assignedCardCode = useMemo(() => {
    if (!selected || selected.status !== 1) return null;
    const hit = suggestions.suppliers.find((c) => pwCleanName(legacySupplierFor(c)?.supplier_name).toUpperCase() === pwCleanName(selected.supplier).toUpperCase());
    return hit ? hit.supplier_code : '__other__';
  }, [selected, suggestions.suppliers, legacySupplierFor]);

  async function enterSuggest(row) {
    if (webOn || (!suggestions.suppliers.length && !suggestions.loading)) return;
    if (edits[row.key] != null && Number(edits[row.key]) !== Number(row.qty) && row.status !== 1) {
      if (!(await commitReviewed(row, valueOf(row), null))) return;
    }
    const at = assignedCardCode ? suggestions.suppliers.findIndex((c) => c.supplier_code === assignedCardCode) : -1;
    setSupCursor(at >= 0 ? at : 0);
    setZone('suggest');
    setSelectedKey(row.key);
    // The panel is always mounted: focus it now. A rAF-deferred focus never
    // ran while the window was in the background (Chromium pauses rAF).
    suggestRef.current?.focus();
  }
  function exitSuggest() {
    setZone('qty');
    focusRow(selectedIndex < 0 ? 0 : selectedIndex);
  }
  async function assignFromCard(card) {
    const row = selected;
    const uni = legacySupplierFor(card);
    const refusal = pwAssignRefusal({
      card, finalized, busy: cardBusy, status: row?.status, qty: row ? valueOf(row) : 0, legacySupplier: uni, store,
    });
    if (!refusal.ok) { if (refusal.error) setError(refusal.error); return; }
    const value = valueOf(row);
    setCardBusy(true);
    try {
      if (row.qtycheck !== 1 || value !== Number(row.qty)) {
        await api.legacyUpdateQtyCheck(store, row.code, value, session);
        patchRow(row.key, { qty: value, qtycheck: 1 });
        addTo(setReviewedHere, row.key);
        dropEdit(row.key);
      }
      const res = await api.legacyAssignSupplier(store, row.code, uni.supplier_code, uni.supplier_name, session);
      patchRow(row.key, { status: res.status, supplier: res.status === 1 ? uni.supplier_name : null, qtycheck: 1 });
      addTo(setStickyKeys, row.key);
      setBanner(`Assigned ${pwCleanName(row.name)} → ${uni.supplier_name} (qty ${pwQty(res.order_qty ?? value)}).`);
      if (res.status === 1) supplierWa.onAssigned(uni.supplier_code);
      const index = visible.findIndex((r) => r.key === row.key);
      setZone('qty');
      focusRow(index + 1);
    } catch (e) {
      setError(e.message);
    } finally {
      setCardBusy(false);
      loadWorkflow();
    }
  }

  // Compare card: place the row with another supplier's line (its real code
  // -> the store's UnifiedSupplierCODE), or with the current supplier (null).
  async function assignFromCompare(row, line) {
    let sup = supplier;
    if (line) {
      sup = legacySupplierFor({ supplier_code: line.supplier_code, supplier_name: line.supplier_name });
      if (!sup) { setError(`${line.supplier_name || `Supplier ${line.supplier_code}`} is not in ${store}'s supplier list.`); return; }
    }
    const index = visible.findIndex((r) => r.key === row.key);
    const res = await toggleAssign(row, sup);
    if (res?.status === 1) focusRow(index + 1);
  }
  function compareLock(row) {
    if (finalized) return 'Order finalized';
    if (row.status === 1) return 'Unassign to move it to another supplier';
    if (row.status !== 0) return 'Closed';
    if (!(valueOf(row) > 0)) return 'Set an order qty to assign';
    return '';
  }

  // ---- keyboard (Order Workspace keys + Right Arrow to the cards) ----
  // I: bring the Previous Decisions panel into view wherever it is docked.
  function openDecisions() {
    setPanel('decisions', { hidden: false });
    if (panels.find((p) => p.key === 'decisions')?.dock === 'side') setDetailHidden(false);
  }
  function onQtyKey(e, row, index) {
    const action = pwQtyKeyAction({
      key: e.key, view, hasSupplier: Boolean(supplier), status: row.status,
      clear: pwIsClearKeypress(e), ctrl: e.ctrlKey, index, last: visible.length - 1,
    });
    if (!action) return;
    e.preventDefault();
    if (action.type === 'nudge') {
      const next = action.delta > 0 ? valueOf(row) + 1 : Math.max(0, valueOf(row) - 1);
      setEdits((cur) => ({ ...cur, [row.key]: next }));
    } else if (action.type === 'commit' && action.zero) {
      skipRow(row, skipMode, action.nextIndex);
    } else if (action.type === 'commit') {
      commitReviewed(row, valueOf(row), action.nextIndex);
    } else if (action.type === 'assign') {
      toggleAssign(row).then((res) => { if (res?.status === 1) focusRow(index + 1); });
    } else if (action.type === 'remove') removeFromList(row, index);
    else if (action.type === 'suggest') enterSuggest(row);
    else if (action.type === 'decisions') openDecisions();
  }
  function onRowKey(e, row, index) {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); focusRow(index + (e.key === 'ArrowDown' ? 1 : -1)); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); enterSuggest(row); }
    else if (e.key === 'i' || e.key === 'I') { e.preventDefault(); openDecisions(); }
  }

  function gotoNextPending() {
    const isPending = (r) => pwState(r, reviewedHere.has(r.key)) === 'pending';
    let index = visible.findIndex((r, i) => i > selectedIndex && isPending(r));
    if (index < 0) index = visible.findIndex(isPending);
    if (index >= 0) focusRow(index);
  }

  // ---- previous decisions (panel) ----
  const shownPanels = panels.filter((p) => !p.hidden && !(p.dock === 'side' && detailHidden));
  const decisionsShown = shownPanels.some((p) => p.key === 'decisions');
  useEffect(() => {
    if (!store || !selected || !decisionsShown) { setDecisions({ loading: false, rows: [] }); return undefined; }
    let cancelled = false;
    setDecisions({ loading: true, rows: [] });
    api.legacyOrderHistory(store, selected.code, session)
      .then((r) => { if (!cancelled) setDecisions({ loading: false, rows: pwAsArray(r) }); })
      .catch(() => { if (!cancelled) setDecisions({ loading: false, rows: [] }); });
    return () => { cancelled = true; };
  }, [store, selected?.key, decisionsShown, session]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---- finalize / export / out-of-stock ----
  function finalize(reopen) {
    const plan = pwFinalizePlan({
      store,
      reopen,
      note: store ? window.prompt(reopen ? 'Why is this order being reopened?' : 'Optional finalization note:') : null,
    });
    if (plan.action !== 'finalize' && plan.action !== 'reopen') return;
    (plan.action === 'reopen' ? api.legacyReopenOrder(store, plan.note, session) : api.legacyFinalizeOrder(store, plan.note, session))
      .then((wf) => {
        setWorkflow(wf);
        // The complete order to every auto-send supplier.
        if (plan.action === 'finalize') supplierWa.sendFinalAll();
      }).catch((e) => setError(e.message));
  }
  const orderNoFor = (dateFolder) => (workflow?.order_no != null ? String(workflow.order_no)
    : workflow?.order_id != null ? String(workflow.order_id) : dateFolder);
  const exportExt = ['csv', 'xlsx'].includes(exportSettings.fileFormat) ? exportSettings.fileFormat : 'xls';

  async function runExport() {
    const blocked = pwExportGuard({ needsSupplier: true, supplier });
    if (blocked) { setError(blocked); return; }
    setExporting(true); setError('');
    try {
      const allProducts = view === 'supplier' && (supplierMode === 'all' || supplierMode === 'site');
      const mode = view === 'supplier' && !allProducts ? supplierMode : 'history';
      const dateFolder = exportKit.dateFolder();
      const orderNo = orderNoFor(dateFolder);
      const columns = exportKit.columnDefs.filter((c) => c.required || exportSettings.columns[c.key]).map((c) => PW_EXPORT_KEY_MAP[c.key]);
      const productCodes = view === 'supplier' ? visible.map((r) => r.key) : undefined;
      const { blob, filename: backendFilename, exportedCount } = await api.legacyExportOrder(
        store, supplier.supplier_code, supplier.supplier_name, mode, Number(splitCount) || 0, session,
        { columns, fileFormat: exportSettings.fileFormat, orderNo, productCodes, allProducts, images: exportSettings.images, remarks: exportRemarks() },
      );
      const filename = `${exportKit.safeFileName(`${supplier.supplier_name} ${store}   ${dateFolder}`)}.${exportExt}`;
      const folderParts = [exportSettings.basePath, dateFolder, exportKit.safePathSegment(orderNo)];
      if (exportSettings.supplierWise) folderParts.push(exportKit.safePathSegment(supplier.supplier_name));
      const written = [];
      const savedTo = await exportKit.save(blob, backendFilename, filename, folderParts.join('\\'), written);
      setLastExport(written.length ? {
        files: written, rememberKey: `supplier:${supplier.supplier_code}`, defaultChat: supplier.supplier_name,
        targets: supplierContact?.targets || [],
        title: `Send ${supplier.supplier_name} order on WhatsApp`, source: 'Order',
      } : null);
      setBanner(savedTo ? `Exported ${exportedCount} product(s) for ${supplier.supplier_name} → ${savedTo}` : `Exported ${exportedCount} product(s) for ${supplier.supplier_name}.`);
      setExportOpen(false);
      setReloadTick((t) => t + 1);
    } catch (e) {
      setError(e.message || 'Export failed.');
    } finally {
      setExporting(false);
    }
  }
  async function runPendingExport() {
    setExporting(true); setError('');
    try {
      const dateFolder = exportKit.dateFolder();
      const orderNo = orderNoFor(dateFolder);
      const { blob, filename: backendFilename, exportedCount } = await api.legacyExportPendingOrder(
        store, Number(splitCount) || 0, session, { fileFormat: exportSettings.fileFormat, orderNo, images: exportSettings.images, remarks: exportRemarks() },
      );
      const filename = `Pending ${dateFolder} ${exportKit.safePathSegment(orderNo)}.${exportExt}`;
      const folderParts = [exportSettings.basePath, dateFolder, exportKit.safePathSegment(orderNo)];
      const written = [];
      const savedTo = await exportKit.save(blob, backendFilename, filename, folderParts.join('\\'), written);
      setLastExport(written.length ? { files: written, rememberKey: 'pending', defaultChat: '', title: 'Send pending order on WhatsApp', source: 'Pending order' } : null);
      setBanner(savedTo ? `Exported ${exportedCount} pending product(s) → ${savedTo}` : `Exported ${exportedCount} pending product(s).`);
      setExportOpen(false);
    } catch (e) {
      setError(e.message || 'Export failed.');
    } finally {
      setExporting(false);
    }
  }
  function removeUnavailable() {
    if (!store || !supplier) return;
    if (!window.confirm(`Check ${supplier.supplier_name}'s stock and remove any assigned products they don't have? They go back to open (qty-checked) for other suppliers.`)) return;
    setRemovingUnavailable(true); setError('');
    api.legacyRemoveUnavailable(store, supplier.supplier_code, session)
      .then(({ removed_count }) => {
        setBanner(removed_count ? `Removed ${removed_count} out-of-stock product(s) from ${supplier.supplier_name}.` : `${supplier.supplier_name} has stock for every assigned product — nothing removed.`);
        setReloadTick((t) => t + 1);
      })
      .catch((e) => setError(e.message))
      .finally(() => setRemovingUnavailable(false));
  }
  function unassignAll() {
    if (!store || !supplier || finalized) return;
    if (!window.confirm(`Unassign ALL ${rows.length} product(s) from ${supplier.supplier_name}? They go back to open (qty-checked) for any supplier.`)) return;
    setRemovingUnavailable(true); setError('');
    api.legacyUnassignAll(store, supplier.supplier_code, session)
      .then(({ removed_count }) => {
        setBanner(`Unassigned ${removed_count} product(s) from ${supplier.supplier_name}.`);
        setReloadTick((t) => t + 1);
      })
      .catch((e) => setError(e.message))
      .finally(() => setRemovingUnavailable(false));
  }

  // ---- totals ----
  const totals = useMemo(() => {
    const t = { products: visible.length, finalQty: 0, reviewed: 0, offers: 0, zero: 0 };
    visible.forEach((r) => {
      const v = Number(edits[r.key] ?? r.qty) || 0;
      t.finalQty += v;
      if (v <= 0) t.zero += 1;
      if (r.offer) t.offers += 1;
      if (pwState(r, reviewedHere.has(r.key)) !== 'pending') t.reviewed += 1;
    });
    t.pending = t.products - t.reviewed;
    return t;
  }, [visible, edits, reviewedHere]);

  // ---- cells ----
  function renderState(row, index, state) {
    // Qty check status: a tick only (owner ruling) -- the assigned supplier
    // is shown in the last column, not here. ⚙ "Text" gives word labels.
    const title = state === 'assigned' && row.supplier ? `Assigned — ${pwCleanName(row.supplier)}` : PW_STATE_LABEL[state];
    const badge = statusStyle === 'text' || state === 'closed'
      ? <span className={`pw-pill pw-pill--${state}`} title={title}>{PW_STATE_LABEL[state]}</span>
      : state === 'pending'
        ? <span className="pw-check pw-check--pending" title={title}>–</span>
        : <span className={`pw-check pw-check--${state === 'checked' ? 'finalized' : state}`} title={title}>{state === 'rejected' ? '0' : '✓'}</span>;
    const supplierView = view === 'supplier' || view === 'assigned';
    const skipPicker = state === 'rejected' && row.status === 0 && !supplierView && (
      <select className="pw-skip-mode" value={row.skipReason || 'current_refresh'} disabled={finalized || savingKey === row.key}
        aria-label="Skip mode" title="Skip mode for this product"
        onClick={(e) => e.stopPropagation()}
        onChange={(e) => skipRow(row, e.target.value, null)}>
        {PW_SKIP_MODES.map(([code, label]) => <option key={code} value={code}>{label}</option>)}
      </select>
    );
    return (
      <span className="pw-state-wrap">
        {badge}
        {skipPicker}
        {siteChecking && supplier && row.status === 0 ? <SiteMark site={site} row={row} disabled={finalized} /> : supplierView && supplier && !finalized && (row.status === 1 ? (
          <button type="button" className="pw-mini-btn pw-mini-btn--danger" disabled={assigningKey === row.key}
            title="Unassign — back to open for any supplier"
            onClick={(e) => { e.stopPropagation(); toggleAssign(row); }}>
            {assigningKey === row.key ? '…' : 'Unassign'}
          </button>
        ) : row.status === 0 && (
          <>
            <button type="button" className="pw-mini-btn pw-mini-btn--ok" disabled={assigningKey === row.key || !(valueOf(row) > 0)}
              title={`Assign to ${supplier.supplier_name} (Enter)`}
              onClick={(e) => { e.stopPropagation(); toggleAssign(row); }}>
              {assigningKey === row.key ? '…' : 'Assign'}
            </button>
            {view === 'supplier' && (
              <button type="button" className="pw-icon-act" title="Remove from this list (Delete) — stays open for another supplier" aria-label="Remove from this list"
                onClick={(e) => { e.stopPropagation(); removeFromList(row, index); }}>✕</button>
            )}
          </>
        ))}
      </span>
    );
  }

  function renderCell(col, row, index, state) {
    switch (col.key) {
      case 'sno': return index + 1;
      case 'name': return (
        <span className="pw-name-wrap">
          <span className="ow-cellname pw-prod-name" title={`${pwCleanName(row.name)} (#${row.key})`}>{pwCleanName(row.name) || `#${row.key}`}</span>
          <AbnormalMark info={abnInfo(row.key)} />
          {supplierView && compareOn && row.status === 0 && (
            <SupplierCompareBadge lines={compare.byCode[row.key]} currentCodes={currentCodes} orderQty={valueOf(row)} />
          )}
        </span>
      );
      case 'offer': return row.offer ? <span title="Has had a free-qty offer in purchase history">🎁</span> : null;
      case 'pack': return pwQty(row.pack);
      case 'unit': return <span className="ow-cellname">{row.unit || '—'}</span>;
      case 'stock': return <span className={row.stock != null && Number(row.stock) <= 0 ? 'ow-stock-zero' : undefined}>{pwQty(row.stock)}</span>;
      case 'sls': return pwQty(row.sls);
      case 'lsd': return pwDaysAgo(row.lsd);
      case 'lrd': return pwDaysAgo(row.lrd);
      case 'mrp': return pwMoney(row.mrp);
      case 'maxqty': return pwQty(row.maxqty);
      case 'sstock': {
        const sup = supplierStock(row);
        return <span className="ow-sstock-val">{sup ? pwQty(sup.stock) : '—'}</span>;
      }
      case 'soffer': {
        const offer = supplierStock(row)?.offer;
        return offer ? <span className="pw-soffer" title={`Supplier offer: buy ${offer.split('+')[0]}, get ${offer.split('+')[1]} free`}>{offer}</span> : '—';
      }
      case 'disc': return pwQty(row.disc);
      case 'minqty': return pwQty(row.minqty);
      case 'rack': return row.rack || '—';
      case 'wanted': return <span className="ow-cellname" title={row.wanted || undefined}>{row.wanted ?? '—'}</span>;
      case 'supplier': return <span className="ow-cellname">{row.supplier ? pwCleanName(row.supplier) : '—'}</span>;
      case 'remarks': return <span className="ow-cellname" title={row.remarks || ''}>{row.remarks || '—'}</span>;
      case 'xremark': {
        const typed = isTyped(row.key);
        const text = typed ? typedNotes[row.key] : offerNote(row);
        return (
          <input
            className={`pw-note${!typed && text ? ' pw-note--auto' : ''}`}
            type="text" maxLength={PW_NOTE_MAX} spellCheck={false} autoComplete="off"
            aria-label={`${pwCleanName(row.name) || `#${row.key}`} export remark`}
            title={!typed && text ? `Offer ${text}: the order qty matches it (auto). Type to change; Esc goes back to auto.`
              : 'Export remark, up to 10 characters (12%, 9+1). Goes into the export only. Esc goes back to auto.'}
            value={text}
            onClick={(e) => e.stopPropagation()}
            onFocus={(e) => { setSelectedKey(row.key); e.target.select(); }}
            onChange={(e) => setNote(row.key, e.target.value)}
            onKeyDown={(e) => onNoteKey(e, row, index)}
          />
        );
      }
      case 'code': return row.key;
      case 'org': return pwQty(row.org);
      case 'diff': {
        const d = Number(edits[row.key] ?? row.qty ?? 0) - Number(row.org ?? 0);
        return Number.isFinite(d) && d !== 0 ? <span className={d > 0 ? 'pw-diff-up' : 'pw-diff-down'}>{d > 0 ? `+${pwQty(d)}` : pwQty(d)}</span> : '—';
      }
      case 'type': return <span className="ow-cellname">{row.type || '—'}</span>;
      case 'offerpat': return Number(row.raw?.LastOfferFreeQty) > 0 ? `${pwQty(row.raw.LastOfferBaseQty)}+${pwQty(row.raw.LastOfferFreeQty)}` : '—';
      case 'lrddate': return pwDate(row.lrd);
      case 'lsddate': return pwDate(row.lsd);
      case 'qty': {
        const value = edits[row.key] ?? row.qty ?? 0;
        const locked = finalized || view === 'assigned' || row.status !== 0;
        return (
          <span className="ow-qty-cell">
            <span className="ow-qty-diff-slot"><PwQtyDiff from={row.org ?? 0} to={value} /></span>
            <input
              ref={(el) => { qtyRefs.current[index] = el; }}
              className={`ow-qty pw-qty${edits[row.key] != null && Number(edits[row.key]) !== Number(row.qty) ? ' pw-qty--dirty' : ''}`}
              type="number" min={0} step={1} inputMode="numeric"
              aria-label={`${pwCleanName(row.name) || `#${row.key}`} order quantity`}
              value={value}
              // readOnly, not disabled, while its own save runs: disabling the
              // focused box throws focus to <body> and the next key is lost.
              disabled={locked}
              readOnly={savingKey === row.key}
              onClick={(e) => e.stopPropagation()}
              onFocus={(e) => { setSelectedKey(row.key); e.target.select(); }}
              onChange={(e) => setEdits((cur) => ({ ...cur, [row.key]: pwWholeQty(e.target.value) }))}
              onKeyDown={(e) => onQtyKey(e, row, index)}
            />
          </span>
        );
      }
      case 'state': return renderState(row, index, state);
      default: return null;
    }
  }

  // ---- detail header facts ----
  const otherStores = suggestions.otherStores;
  const holding = otherStores.filter((s) => Number(s.stock) > 0).length + (Number(selected?.stock) > 0 ? 1 : 0);
  const latestCard = suggestions.suppliers.find((s) => s.tags?.includes('latest'));
  const latestPurchase = pwGrnForSelection(latestGrn, selected?.key);
  const visibleCodes = useMemo(() => visible.map((r) => r.code), [visible]);
  const cardsAvailable = Boolean(platformStore && tenantId);
  const assignQty = selected ? valueOf(selected) : 0;

  let orderContext = 'Loading order…';
  if (!store) orderContext = 'No store';
  else if (orderHeader?.error) orderContext = 'Order info unavailable';
  else if (orderHeader && orderHeader.order_id == null) orderContext = 'No active order';
  // order_no restarts at 1 every day, so also show the full OrderId and the
  // order's Wanted date/time -- otherwise yesterday's #1 and today's #1 look
  // identical and a stale grid can't be told apart from a fresh one.
  else if (orderHeader) {
    const no = orderHeader.order_no != null ? `Order #${orderHeader.order_no} · ${orderHeader.order_id}` : `Order #${orderHeader.order_id}`;
    const wanted = pwDateTime(orderHeader.order_datetime);
    orderContext = wanted ? `${no} · Wanted ${wanted}` : no;
  }
  const orderUpdated = orderHeader?.updated_at ? pwDateTime(orderHeader.updated_at) : '';
  const showExport = view === 'supplier' || view === 'assigned' || process.key === 'pending';
  const needsSupplier = (view === 'supplier' && supplierMode !== 'all') || view === 'assigned';

  const items = virt.getVirtualItems();
  const padTop = items.length ? items[0].start : 0;
  const padBottom = items.length ? virt.getTotalSize() - items[items.length - 1].end : 0;

  // ---- All Stores click: show another store's Trend / Purchase / Sales ----
  // peek = { store, code } (OrderNMC StoreName = store_code, that store's own
  // product code). Returns to this store as soon as focus moves on: another
  // product or store, or a click anywhere outside All Stores and the panels
  // showing the peek (an open invoice/bill card does not count).
  const [peek, setPeek] = useState(null);
  const recordOpenRef = useRef(false);
  recordOpenRef.current = Boolean(record);
  useEffect(() => { setPeek(null); }, [selected?.key, store]);
  useEffect(() => {
    if (!peek) return undefined;
    const onDown = (e) => {
      if (recordOpenRef.current || e.target.closest?.('[data-peek-zone]')) return;
      setPeek(null);
    };
    document.addEventListener('mousedown', onDown, true);
    return () => document.removeEventListener('mousedown', onDown, true);
  }, [peek]);
  const pickStore = useCallback((row) => {
    setPeek((cur) => (row.current || (cur && cur.store === row.store_code) ? null : { store: row.store_code, code: row.product_code }));
  }, []);
  const detailStore = peek ? peek.store : store;
  const detailCode = peek ? peek.code : (selected?.code ?? null);

  // ---- detail panels, placed by the layout settings ----
  const midPanels = shownPanels.filter((p) => p.dock === 'middle');
  const sidePanels = shownPanels.filter((p) => p.dock === 'side');
  const bottomPanels = shownPanels.filter((p) => p.dock === 'bottom');
  const renderPanel = (p) => {
    if (p.key === 'suggest') {
      return (
        <Fragment key="suggest">
          {cardsAvailable ? (
            <SuggestionPanel
              panelRef={suggestRef}
              suggestions={suggestions}
              hasProduct={Boolean(selected)}
              productMrp={selected?.mrp ?? null}
              active={zone === 'suggest'}
              cursor={supCursor}
              onCursor={setSupCursor}
              onAssign={assignFromCard}
              onExit={exitSuggest}
              assignQty={assignQty}
              assignedSupplier={assignedCardCode}
              canAssign={Boolean(selected) && !finalized && selected.status === 0 && assignQty > 0}
              busy={cardBusy}
            />
          ) : (
            <section className="sg-panel">
              <div className="sg-head"><span className="sg-title">Supplier Recommendation</span></div>
              <div className="sg-body"><div className="sg-none">{store ? `${store} is not set up as a Nexora store, so there are no recommendations for it.` : 'Pick a store.'}</div></div>
            </section>
          )}
        </Fragment>
      );
    }
    if (p.key === 'stores') {
      return (
        <StoreTrendsPanel key="stores" layout={p.dock === 'bottom' ? 'cards' : 'rows'}
          tenantId={tenantId} storeId={platformStore?.store_id || ''}
          productCode={selected ? selected.key : null} session={session}
          peekStore={peek?.store ?? null} onPick={pickStore} />
      );
    }
    if (p.key === 'facts') {
      return (
        <section className="ow-panel pw-facts-panel" key="facts">
              {selected ? (
                <>
                  <div className="pw-dhead-main">
                    <div className="pw-dhead-title">
                      <strong title={pwCleanName(selected.name)}>{pwCleanName(selected.name) || `#${selected.key}`}</strong>
                      <span className="pw-dhead-meta">
                        {[
                          selected.key,
                          selected.unit,
                          selected.pack != null ? `Pack ${pwQty(selected.pack)}` : null,
                          suggestions.data ? `${holding}/${otherStores.length + 1} Stores` : null,
                          latestCard?.ptr != null ? `Last ${pwRupees(latestCard.ptr)}` : null,
                        ].filter(Boolean).join(' • ')}
                      </span>
                    </div>
                    {(() => {
                      // Quantities, then the latest GRN's prices, as one tile grid.
                      // GRN facts only once they belong to THIS product -- no
                      // stale values from the previous row, no fake zeros.
                      const grn = latestPurchase;
                      const finalQty = edits[selected.key] ?? selected.qty;
                      const changed = selected.org != null && Number(selected.org) !== Number(finalQty);
                      const pct = (v) => (v == null || v === '' ? '—' : `${pwQty(v)}%`);
                      return (
                        <>
                          <dl className="pw-facts pw-facts--tiles">
                            <div><dt>Original</dt><dd>{pwQty(selected.org)}</dd></div>
                            <div><dt>Final</dt><dd className={changed ? (Number(finalQty) > Number(selected.org) ? 'is-up' : 'is-down') : undefined}>{pwQty(finalQty)}</dd></div>
                            <div><dt>Stock</dt><dd className={selected.stock != null && Number(selected.stock) <= 0 ? 'is-zero' : undefined}>{pwQty(selected.stock)}</dd></div>
                            <div><dt>90d sales</dt><dd className="is-sales">{pwQty(selected.sls)}</dd></div>
                            {selected.maxqty != null && <div><dt>Max sale</dt><dd>{pwQty(selected.maxqty)}</dd></div>}
                            {selectedSup && <div><dt>Sup. stock</dt><dd>{pwQty(selectedSup.stock)}</dd></div>}
                            {selectedSup?.offer && <div><dt>Sup. offer</dt><dd className="pw-soffer">{selectedSup.offer}</dd></div>}
                            <div className="is-price" title="Latest GRN"><dt>Cost</dt><dd>{grn ? pwMoney(grn.cost) : '—'}</dd></div>
                            <div className="is-price" title="Latest GRN"><dt>PTR</dt><dd>{grn ? pwMoney(grn.ptr) : '—'}</dd></div>
                            <div className="is-price"><dt>MRP</dt><dd>{selected.mrp != null ? pwMoney(selected.mrp) : grn ? pwMoney(grn.purchaseMrp) : '—'}</dd></div>
                            <div className="is-price" title="Latest GRN"><dt>Disc</dt><dd>{grn ? pct(grn.discount) : '—'}</dd></div>
                            <div className="is-price" title="Latest GRN"><dt>Received</dt><dd>{grn ? pwQty(grn.receivedQty) : '—'}</dd></div>
                            <div className="is-price" title="Latest GRN"><dt>Free</dt><dd>{grn ? pwQty(grn.freeQty) : '—'}</dd></div>
                          </dl>
                          <div className="pw-dhead-facts">
                            <span title="Supplier of the latest GRN"><b>Supplier</b>{grn?.supplier ? pwCleanName(grn.supplier) : '—'}</span>
                            <span><b>Last sale</b>{pwDate(grn?.lastSaleDate || selected.lsd)}</span>
                            <span><b>Last GRN</b>{pwDate(grn?.grnDate || selected.lrd)}</span>
                            {selected.wanted && <span><b>Wanted</b>{selected.wanted}</span>}
                            {selected.offer && <span><b>Offer</b>🎁</span>}
                            {selected.supplier && <span><b>Order supplier</b>{pwCleanName(selected.supplier)}</span>}
                          </div>
                        </>
                      );
                    })()}
                  </div>
                </>
              ) : <span className="ow-side-hint">Select a product to see its trend, purchase &amp; sales.</span>}
        </section>
      );
    }
    if (p.key === 'decisions') {
      return (
        <Fragment key="decisions">
                <section className="ow-panel pw-decisions">
                  <div className="ow-panel-title">Previous Decisions{decisions.rows.length > 0 && <span className="ow-panel-count">Last {Math.min(decisions.rows.length, 25)}</span>}</div>
                  <div className="ow-panel-scroll">
                    <table className="ow-intel-table">
                      <thead><tr><th className="ow-num">Or Qty</th><th className="ow-num">Org</th><th className="ow-num">Pack</th><th className="ow-num">MRP</th><th>Remarks</th><th>Wanted date</th><th>Wanted</th><th>Supplier</th></tr></thead>
                      <tbody>
                        {decisions.rows.map((h, i) => (
                          <tr key={i}><td className="ow-num">{pwQty(h.Orqty)}</td><td className="ow-num">{pwQty(h.OrgOrderQty)}</td><td className="ow-num">{pwQty(h.saleunit)}</td><td className="ow-num">{pwMoney(h.MRP)}</td><td>{h.remarks ?? '—'}</td><td>{pwDate(h.Wanteddate)}</td><td>{h.WantedType ?? '—'}</td><td>{h.Orsupplier ?? '—'}</td></tr>
                        ))}
                        {!decisions.rows.length && <tr><td colSpan={8} className="ow-empty">{!selected ? 'Select a product.' : decisions.loading ? 'Loading…' : 'No previous-order history for this product.'}</td></tr>}
                      </tbody>
                    </table>
                  </div>
                </section>
        </Fragment>
      );
    }
    // Trend / Purchase / Sales: this store, or the store picked in All Stores
    // (title tagged with it). display:contents keeps the dock's flex layout.
    return store ? (
      <div key={p.key} className={`pw-peek-zone${peek ? ' is-peek' : ''}`} data-peek-zone=""
        style={peek ? { '--pw-peek-label': JSON.stringify(` · ${peek.store} #${peek.code}`) } : undefined}>
        <IntelPanel
          sections={[p.key]}
          trendFit={PW_TREND_FIT}
          store={detailStore}
          productCode={detailCode}
          visibleCodes={peek ? [] : visibleCodes}
          mode="local"
          session={session}
          onError={setError}
          onPurchaseSelect={(row) => setRecord({ kind: 'purchase', row, productCode: detailCode, store: detailStore })}
          onSalesSelect={(row) => setRecord({ kind: 'sales', row, productCode: detailCode, store: detailStore })}
        />
      </div>
    ) : null;
  };

  return (
    <section className={`screen-panel ow-screen pw-screen ow-rows-${layout.rowSize} ow-weight-${layout.rowWeight}${hidden ? ' ow-screen-hidden' : ''}`}>
      <div className="pw-topbar">
        <h2 className="pw-title">Procurement</h2>
        <select className="pw-select pw-store-select" value={store} onChange={(e) => setStore(e.target.value)} aria-label="Store" title="Store">
          {!stores.length && <option value="">No stores</option>}
          {stores.map((s) => <option key={s.store_name} value={s.store_name}>{s.store_name}</option>)}
        </select>
        <span className="pw-seg pw-seg--process" role="tablist" aria-label="Process">
          {PW_PROCESSES.map((p) => (
            <button key={p.key} type="button" role="tab" aria-selected={processKey === p.key}
              className={`${processKey === p.key ? 'active' : ''}${p.abnormal ? ' pw-tab--abn' : ''}`.trim() || undefined}
              title={p.abnormal ? 'Products with a bill above 5× their usual bill sale — mark “don\'t consider in order”' : undefined}
              onClick={() => pickProcess(p.key)}>
              {p.abnormal ? '⚠ Abnormal' : p.label}
              {processKey === p.key
                ? <span className="pw-seg-count">{loading ? '…' : visible.length}</span>
                : p.abnormal && (abnormal.loading || abnormal.abnormalCount > 0) && <span className="pw-seg-count">{abnormal.loading ? '…' : abnormal.abnormalCount}</span>}
            </button>
          ))}
        </span>
        {/* Order chip + reload + settings stay together at the right edge
            (wrapping as one unit), so the settings card opens on-screen. */}
        <span className="pw-topbar-end">
        <span className="pw-order-chip" title={[orderContext, orderUpdated ? `Updated ${orderUpdated}` : ''].filter(Boolean).join(' · ')}>
          {orderContext}{orderUpdated ? ` · ${orderUpdated}` : ''}
        </span>
        <button type="button" className="pw-round-btn" disabled={!store || loading} title="Reload from the server" aria-label="Reload"
          onClick={() => { setReloadTick((t) => t + 1); setAbnTick((t) => t + 1); loadWorkflow(); }}>⟳</button>
        <div className="pw-settings-wrap" ref={settingsRef}>
          <button type="button" className="pw-round-btn" title="Procurement settings" aria-label="Procurement settings" aria-expanded={settingsOpen} onClick={() => setSettingsOpen((v) => !v)}>
            <PwIcon path={PW_GEAR_PATH} />
          </button>
          {settingsOpen && (
            <div className="pw-settings pw-settings--panes" role="dialog" aria-label="Procurement settings">
              <div className="pw-settings-pane">
              <span className="pw-section-label">Qty check status</span>
              <div className="ow-tabs" role="radiogroup" aria-label="Qty check status">
                {PW_STATUS_STYLES.map(([key, label]) => (
                  <button key={key} type="button" role="radio" aria-checked={statusStyle === key} className={statusStyle === key ? 'active' : ''} onClick={() => setStatusStyle(key)}>{label}</button>
                ))}
              </div>
              <span className="pw-settings-hint">{statusStyle === 'tick' ? '✓ reviewed · – not reviewed · 0 rejected' : 'Not Reviewed / Reviewed / Rejected / Assigned'}</span>
              <span className="pw-section-label">Columns <small>(show, move, width · empty columns hide themselves)</small></span>
              <ul className="pw-col-list">
                {colOrder.map((key, i) => {
                  const c = PW_COLUMNS.find((x) => x.key === key);
                  if (!c) return null;
                  const on = c.fixed || shownCols.includes(key);
                  return (
                    <li key={key} className={`pw-col-list__row${on ? '' : ' is-off'}`} title={c.title}>
                      <label className="pw-col-list__name">
                        <input type="checkbox" checked={on} disabled={c.fixed}
                          onChange={(e) => setShownCols((cur) => (e.target.checked ? [...cur, key] : cur.filter((k) => k !== key)))} />
                        <span>{c.menu || (c.key === 'offer' ? 'Offer 🎁' : c.key === 'state' ? 'State (QCheck)' : c.label)}</span>
                      </label>
                      <button type="button" className="pw-col-list__mv" disabled={i === 0} aria-label={`Move ${c.label} left`} onClick={() => moveCol(key, -1)}>▲</button>
                      <button type="button" className="pw-col-list__mv" disabled={i === colOrder.length - 1} aria-label={`Move ${c.label} right`} onClick={() => moveCol(key, 1)}>▼</button>
                      {key === 'state'
                        ? <span className="pw-col-list__auto">auto</span>
                        : <input type="number" min={24} max={400} className="pw-col-list__w" aria-label={`${c.label} width`}
                            placeholder={String(c.width || '')} value={colWidths[key] ?? ''}
                            onChange={(e) => setColWidths((cur) => {
                              const next = { ...cur };
                              if (e.target.value === '') delete next[key]; else next[key] = Number(e.target.value);
                              return next;
                            })} />}
                    </li>
                  );
                })}
              </ul>
              <button type="button" className="ow-btn ow-btn-sm" onClick={resetColumns}>Default columns</button>
              </div>
              <div className="pw-settings-pane">
                <span className="pw-section-label">Panels <small>(show, dock &amp; order)</small></span>
                <ul className="pw-col-list pw-panel-list">
                  {panels.map((p, i) => {
                    const def = PW_PANEL_DEFS.find((d) => d.key === p.key);
                    return (
                      <li key={p.key} className={`pw-panel-row${p.hidden ? ' is-off' : ''}`}>
                        <label className="pw-col-list__name">
                          <input type="checkbox" checked={!p.hidden} onChange={() => setPanel(p.key, { hidden: !p.hidden })} />
                          <span>{def?.label}</span>
                        </label>
                        <span className="pw-dock-seg" role="group" aria-label={`${def?.label} position`}>
                          {PW_DOCKS.map(([dock, label]) => (
                            <button key={dock} type="button" className={p.dock === dock ? 'active' : undefined} onClick={() => setPanel(p.key, { dock })}>{label}</button>
                          ))}
                        </span>
                        <button type="button" className="pw-col-list__mv" disabled={i === 0} aria-label={`Move ${def?.label} up`} onClick={() => movePanel(i, -1)}>▲</button>
                        <button type="button" className="pw-col-list__mv" disabled={i === panels.length - 1} aria-label={`Move ${def?.label} down`} onClick={() => movePanel(i, 1)}>▼</button>
                      </li>
                    );
                  })}
                </ul>
                <span className="pw-settings-hint">Middle = beside the grid · Side = right column · Bottom = under the grid</span>
                <button type="button" className="ow-btn ow-btn-sm" onClick={() => setPanels(pwNormalizePanels(null))}>Default panels</button>
                <label className="pw-col-toggle">
                  <input type="checkbox" checked={!detailHidden} onChange={(e) => setDetailHidden(!e.target.checked)} /> Show side column
                </label>
                <label className="pw-col-toggle" title="By Supplier / Supplier Orders: other suppliers' stock, offer and Disc% under the current row">
                  <input type="checkbox" checked={compareOn} onChange={(e) => setCompareOn(e.target.checked)} /> Compare suppliers under row
                </label>
                <label className="pw-col-toggle" title="Open the other suppliers' stock card under the current row; off keeps it hidden">
                  <input type="checkbox" checked={compareOn && compareCardOn} disabled={!compareOn} onChange={(e) => setCompareCardOn(e.target.checked)} /> Show other-supplier stock card
                </label>
              </div>
            </div>
          )}
        </div>
        </span>
      </div>

      <div className="pw-filterbar">
        {(view === 'supplier' || view === 'assigned') && (
          <span className="pw-supplier-pick" title="Supplier">
            <SupplierPicker suppliers={suppliers} value={supplier} onChange={setSupplier} />
          </span>
        )}
        {view === 'supplier' && (
          <span className="pw-seg pw-seg--small" role="tablist" aria-label="Supplier list">
            {PW_SUPPLIER_MODES.map(([key, label]) => (
              <button key={key} type="button" role="tab" aria-selected={supplierMode === key} className={supplierMode === key ? 'active' : undefined}
                title={key === 'all' ? 'Every open orderable product, not just this supplier’s match'
                  : key === 'site' ? 'Check every open, unassigned product on this supplier’s website' : undefined}
                onClick={() => setSupplierMode(key)}>{label}</button>
            ))}
            {supplierMode !== 'site' && supplier && (
              <button type="button" className={siteCheckOn ? 'active' : undefined} aria-pressed={siteCheckOn}
                title="Check these products on the supplier's website (opens the site on the right)"
                onClick={() => setSiteCheckOn((v) => !v)}>🌐 Check in site</button>
            )}
          </span>
        )}
        <span className="pw-search">
          <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m15.5 15.5 5 5" /></svg>
          <input type="search" placeholder="Search product or code…" value={search} onChange={(e) => setSearch(e.target.value)} />
        </span>
        <select className="pw-select" value={productType} onChange={(e) => setProductType(e.target.value)} aria-label="Product type">
          {PW_PRODUCT_TYPES.map((t) => <option key={t} value={t}>{t === 'All' ? 'All types' : t}</option>)}
        </select>
        <select className="pw-select pw-wanted-select" value={wantedFilter} onChange={(e) => setWantedFilter(e.target.value)} aria-label="Wanted" title={wantedFilter}>
          <option value="All">Wanted: all</option>
          {wantedOptions.map((w) => <option key={w} value={w}>Wanted: {w}</option>)}
        </select>
        {/* Right-hand group wraps as one unit, so Export / skip mode never run
            off the window edge on narrow screens; only the key hints hide. */}
        <span className="pw-filter-end">
        <span className="pw-keys">
          {view === 'assigned' ? <><kbd>↕</kbd> Move <kbd>→</kbd> Suppliers</>
            : <><kbd>↕</kbd> Review &amp; move <kbd>Enter</kbd> {view === 'supplier' && supplier ? 'Assign' : 'Save'}{view === 'supplier' ? <> <kbd>Del</kbd> Remove</> : null} <kbd>→</kbd> Suppliers</>}
        </span>
        {view !== 'assigned' && (
          <label className="pw-esc-skip" title="What Esc does: skip this order only, or keep skipping in later orders until the product sells again">
            <kbd>Esc</kbd> Skip
            <select className="pw-skip-mode" value={skipMode} onChange={(e) => setSkipMode(e.target.value)} aria-label="Esc skip mode">
              {PW_SKIP_MODES.map(([code, label]) => <option key={code} value={code}>{label}</option>)}
            </select>
          </label>
        )}
        <span className="pw-filter-actions">
          {view === 'assigned' && (
            <button type="button" className="ow-btn ow-btn-sm" disabled={!supplier || removingUnavailable}
              title={supplier ? "Check this supplier's stock and unassign anything they don't have" : 'Pick a supplier first'}
              onClick={removeUnavailable}>{removingUnavailable ? 'Checking…' : 'Remove out-of-stock'}</button>
          )}
          {view === 'assigned' && (
            <button type="button" className="ow-btn ow-btn-sm" disabled={!supplier || finalized || removingUnavailable || !rows.length}
              title={supplier ? 'Unassign every product from this supplier — back to open for any supplier' : 'Pick a supplier first'}
              onClick={unassignAll}>Unassign all</button>
          )}
          {supplier && (
            <button type="button" className={`ow-btn ow-btn-sm${supplierContact ? ' pw-wa-on' : ''}`}
              title={supplierContact ? `WhatsApp: ${supplierContact.targets.map((t) => t.name).join(', ')}${supplierContact.auto_send ? ` · auto every ${supplierContact.batch_size}` : ''}` : 'Set this supplier’s WhatsApp group / contacts'}
              onClick={() => setWaContactOpen(true)}>💬 WhatsApp{supplierContact?.auto_send ? ' · Auto' : ''}</button>
          )}
          {showExport && (
            <button type="button" ref={exportBtnRef} className="ow-btn ow-btn-sm" disabled={process.key !== 'pending' && !supplier}
              title={process.key === 'pending' ? 'Export pending (reviewed, not assigned) products' : supplier ? 'Export this supplier’s order' : 'Pick a supplier first'}
              aria-expanded={exportOpen} onClick={() => setExportOpen((v) => !v)}>⬇ Export</button>
          )}
          {view !== 'assigned' && (
            <button type="button" className={`ow-btn ow-btn-sm${bulkOpen ? ' ow-btn-primary' : ''}`} disabled={finalized} aria-pressed={bulkOpen}
              title="Assign every reviewed product to the best supplier by purchase history — one click, no website, no screen switching"
              onClick={() => setBulkOpen((v) => !v)}>⚡ Auto Assign</button>
          )}
          <button type="button" className="ow-btn ow-btn-sm" aria-pressed={webOn} onClick={() => setWebOn((v) => !v)}
            title={webOn ? 'Back to supplier cards and product details' : 'Supplier websites beside the grid'}>🌐 Sites</button>
          {!webOn && (
            <button type="button" className="ow-btn ow-btn-sm" aria-pressed={!detailHidden} onClick={() => setDetailHidden((v) => !v)}>
              {detailHidden ? 'Show details' : 'Hide details'}
            </button>
          )}
        </span>
        </span>
      </div>
      {siteChecking && supplier && (
        <>
          <SiteCheckBar site={site} total={visible.length} siteName={sitePortal?.url ? pwCleanName(supplier.supplier_name) : ''} supplierName={pwCleanName(supplier.supplier_name)}
            busy={siteAssigning || finalized} onConfirm={confirmSiteOrder}
            extra={(
              <>
                <button type="button" className="ow-btn ow-btn-sm" disabled={harvestHook.busy || !sitePortal?.url}
                  title={harvestHook.busy
                    ? 'Reading the whole stock in the background — you can still Check products one by one below'
                    : `Read the supplier's whole stock once into Live Stock${harvestHook.avgMs ? ` — usually about ${fmtDur(harvestHook.avgMs)}` : ''}`}
                  onClick={harvestHook.harvest}>
                  {harvestHook.busy ? 'Reading stock…' : `↻ Harvest stock${harvestHook.avgMs ? ` (~${fmtDur(harvestHook.avgMs)})` : ''}`}
                </button>
                <button type="button" className="ow-btn ow-btn-sm"
                  title="Map this supplier's products to the store's products"
                  onClick={() => { setShowMapReview((v) => !v); if (!matchReview.review) matchReview.load(); }}>
                  Map products…
                </button>
              </>
            )} />
          {harvestHook.progress && (
            <div className="ow-banner" role="status">
              {harvestHook.progress}
              {harvestHook.busy && <span className="pw-sitebar-left"> — no need to wait: use “Check” on any product to order it now.</span>}
            </div>
          )}
          {harvestHook.error && <div className="ow-banner" role="alert">{harvestHook.error}</div>}
          {matchReview.error && <div className="ow-banner" role="alert">{matchReview.error}</div>}
          {showMapReview && (
            <MatchReview review={matchReview.review} busy={matchReview.busy}
              storeProducts={visible.map((r) => ({ product_code: r.product_code || r.key, product_name: pwCleanName(r.name) }))}
              onConfirm={matchReview.confirm} />
          )}
        </>
      )}

      {exportOpen && process.key === 'pending' && (
        <ExportCard
          anchorRef={exportBtnRef} splitCount={splitCount} setSplitCount={setSplitCount} exporting={exporting}
          scopeLabel={`Pending (${visible.length} product${visible.length === 1 ? '' : 's'})`}
          onExport={runPendingExport} onClose={() => setExportOpen(false)}
          exportSettings={exportSettings} onUpdateExportSettings={updateExportSettings}
          headline="Read-only — no supplier assignment. Downloads every pending (reviewed, not yet assigned) product."
          showColumns={false} showSupplierWise={false}
        />
      )}
      {exportOpen && process.key !== 'pending' && (
        <ExportCard
          anchorRef={exportBtnRef} splitCount={splitCount} setSplitCount={setSplitCount} exporting={exporting}
          scopeLabel={view === 'assigned' ? `${supplier?.supplier_name || 'selected supplier'} (assigned)` : `${supplier?.supplier_name || 'selected supplier'}`}
          onExport={runExport} onClose={() => setExportOpen(false)}
          exportSettings={exportSettings} onUpdateExportSettings={updateExportSettings}
        />
      )}
      {bulkOpen && (
        <div className="pw-bulkcard">
          <div className="pw-bulkcard-head">
            <b>Auto Assign · by purchase history</b>
            <span>Best margin of the last supplies, else the most-frequent supplier. One click — no website.</span>
            <button type="button" className="wp-btn" aria-label="Close" onClick={() => setBulkOpen(false)}>✕</button>
          </div>
          <OwBulkAssign store={store} session={session} finalized={finalized} reloadKey={reloadTick}
            selectedCode={bulkSel} onSelect={setBulkSel}
            onAssign={assignCheckStock ? assignWithStockCheck : undefined}
            confirmText={assignCheckStock
              ? 'For suppliers with a web order site, check each product’s live stock there, then assign the ones in stock? (nothing is ordered)'
              : undefined}
            extraControls={(
              <label className="pw-bulk-opt" title="Suppliers with a web order portal: confirm live stock on their own site before assigning. Suppliers without a portal are assigned by history.">
                <input type="checkbox" checked={assignCheckStock} onChange={(e) => setAssignCheckStock(e.target.checked)} /> Check stock on supplier sites
              </label>
            )}
            onAssigned={(res) => {
              setBanner(res?.message || (res?.assigned_count != null
                ? `Auto-assigned ${res.assigned_count} product(s) by purchase history. See Supplier Orders.`
                : 'Auto-assigned by purchase history. See Supplier Orders.'));
              setReloadTick((t) => t + 1);
              setBulkOpen(false);
            }}
            onError={setError} />
        </div>
      )}
      {banner && (() => {
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
      {supplierWa.busy && <div className="ow-banner" role="status"><span>{supplierWa.busy}</span></div>}
      {waContactOpen && supplier && (
        <SupplierWhatsAppDialog store={store} supplier={supplier} contact={supplierContact} session={session}
          onClose={() => setWaContactOpen(false)} onSaved={() => supplierWa.reload()} />
      )}
      {waSendOpen && lastExport && (
        <WhatsAppSendDialog {...lastExport} onClose={() => setWaSendOpen(false)} onSent={(chat) => setBanner(`Sent on WhatsApp to ${chat}.`)} />
      )}
      {error && (
        <div className="ow-error" role="alert">
          {error}
          <button type="button" onClick={() => setError('')} aria-label="Dismiss">×</button>
        </div>
      )}

      <div className={webOn ? 'pw-body pw-body--web' : `pw-body${midPanels.length ? '' : ' pw-body--nomid'}${sidePanels.length ? '' : ' pw-body--nodetail'}`}
        style={{ '--pw-grid-w': `${gridWidth}px` }}>
        <div className="pw-gridcol">
          {selected && abnInfo(selected.key) && (
            <AbnormalSalesStrip
              info={abnInfo(selected.key)}
              productName={pwCleanName(selected.name)}
              multipliers={{ abnormal: abnormal.abnormal, warning: abnormal.warning }}
              busy={abnormal.busy}
              readOnly={finalized}
              onToggle={toggleAbnormal}
              infoOnly={!abnormalView}
            />
          )}
          <div className="ow-grid pw-gridbox" ref={gridRef}>
            <table className="ow-fixed pw-grid" style={{ minWidth: `${columns.reduce((t, c) => t + (c.width || 0), 0) + PW_PRODUCT_MIN}px` }}>
              <colgroup>{columns.map((c) => <col key={c.key} style={c.width ? { width: `${c.width}px` } : undefined} />)}</colgroup>
              <thead>
                <tr>
                    {columns.map((c) => (
                    <th key={c.key} title={c.title} className={[c.key === 'qty' ? 'ow-num ow-orqty-col' : c.align === 'right' ? 'ow-num' : c.align === 'center' ? 'pw-center' : '', c.key === 'sno' ? 'pw-sno' : '', c.key === 'name' ? 'pw-name-col' : '', c.key === 'xremark' ? 'pw-note-col' : ''].filter(Boolean).join(' ') || undefined}>
                      {c.key === 'qty'
                        ? <span className="ow-qty-header-cell"><span className="ow-qty-diff-slot" aria-hidden="true" /><span className="ow-qty-header-label">{c.label}</span></span>
                        : c.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {padTop > 0 && <tr aria-hidden="true" className="pw-pad"><td colSpan={columns.length} style={{ '--pw-pad-h': `${padTop}px` }} /></tr>}
                {items.map((item) => {
                  const index = item.index;
                  const row = visible[index];
                  if (!row) return null;
                  const state = pwState(row, reviewedHere.has(row.key));
                  const withCard = cardKey === row.key;
                  return (
                    <Fragment key={row.key}>
                    <tr data-index={index} ref={withCard ? undefined : virt.measureElement}
                      className={`pw-row pw-row--${state}${selectedKey === row.key ? ' ow-row-sel' : ''}${withCard ? ' pw-row--carded' : ''}`}
                      onClick={() => focusRow(index)}>
                      {columns.map((c, ci) => (
                        <td key={c.key}
                          className={[c.key === 'qty' ? 'ow-num ow-orqty-col' : c.align === 'right' ? 'ow-num' : c.align === 'center' ? 'pw-center' : c.key === 'state' ? 'pw-state-cell' : '', c.key === 'sno' ? 'pw-sno' : '', c.key === 'name' ? 'pw-name-col' : '', c.key === 'xremark' ? 'pw-note-col' : ''].filter(Boolean).join(' ') || undefined}
                          {...(ci === 0 ? {
                            tabIndex: -1,
                            ref: (el) => { rowRefs.current[index] = el; },
                            onKeyDown: (e) => onRowKey(e, row, index),
                          } : {})}>
                          {renderCell(c, row, index, state)}
                        </td>
                      ))}
                    </tr>
                    {withCard && (
                      <tr key={`cmp-${row.key}`} ref={cardRowRef} className="pw-cmp-tr">
                        <td colSpan={columns.length}>
                          <SupplierCompareCard
                            lines={compareLines} currentCodes={currentCodes}
                            currentName={supplier?.supplier_name} orderQty={valueOf(row)}
                            assignedName={row.status === 1 ? row.supplier : null}
                            canAssign={view === 'supplier' && !compareLock(row)} lockedReason={compareLock(row)}
                            busy={assigningKey === row.key}
                            onAssign={(line) => assignFromCompare(row, line)}
                          />
                        </td>
                      </tr>
                    )}
                    </Fragment>
                  );
                })}
                {padBottom > 0 && <tr aria-hidden="true" className="pw-pad"><td colSpan={columns.length} style={{ '--pw-pad-h': `${padBottom}px` }} /></tr>}
                {!visible.length && (
                  <tr><td colSpan={columns.length} className="ow-empty">
                    {loading ? `Loading ${process.label}…`
                      : error ? 'Could not load — see the error above.'
                        : !store ? 'Pick a store.'
                          : needsSupplier && !supplier ? 'Pick a supplier to load its products.'
                            : abnormalView ? 'No abnormal sales left to review — continue in Qty Check.'
                              : rows.length ? 'No products match.' : `No products in ${process.label}.`}
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
          {bottomPanels.length > 0 && <div className="pw-bottom-dock">{bottomPanels.map((p) => renderPanel(p))}</div>}
        </div>

        {webOn && <div className="pw-webcol"><WebPanel key={store} ref={webRef} store={store} session={session} suppliers={suppliers} supplierCode={supplier?.supplier_code || ''} onPortal={setSitePortal} /></div>}
        {!webOn && midPanels.length > 0 && <div className="pw-supcol">{midPanels.map((p) => renderPanel(p))}</div>}
        {!webOn && sidePanels.length > 0 && (
          <aside className="pw-detail">
            <div className="ow-side-panels pw-detail-panels">{sidePanels.map((p) => renderPanel(p))}</div>
          </aside>
        )}
        {store && (
          // Publishes the latest GRN to Product Summary even when the
          // Purchase panel is hidden (no section of its own; shared cache).
          <IntelPanel key="latest-grn" sections={[]} trendFit={PW_TREND_FIT} store={store} productCode={selected?.code ?? null}
            visibleCodes={visibleCodes} mode="local" session={session} onError={setError} onLatest={onLatestPurchase} />
        )}
      </div>

      <div className="pw-footbar" role="status">
        <span className="pw-stat"><span>Products</span><b>{pwQty(totals.products)}</b></span>
        <span className="pw-stat"><span>Current row</span><b>{selectedIndex >= 0 ? `${selectedIndex + 1} / ${visible.length}` : '—'}</b></span>
        <span className="pw-stat"><span>Qty check</span><b className={totals.pending > 0 ? 'pw-warn' : undefined}>{pwQty(totals.reviewed)}/{pwQty(totals.products)}</b></span>
        <span className="pw-stat"><span>Final qty</span><b>{pwQty(totals.finalQty)}</b></span>
        <span className="pw-stat"><span>Qty 0</span><b>{pwQty(totals.zero)}</b></span>
        <span className="pw-stat"><span>Offers</span><b>{pwQty(totals.offers)}</b></span>
        {workflow && (
          <span className="pw-stat pw-stat--soft" title="Whole order, from the order workflow">
            <span>Order</span>
            <b>{pwQty(workflow.total_lines)} lines · {pwQty(workflow.assigned_lines)} assigned · {pwQty(workflow.unassigned_lines)} open</b>
          </span>
        )}
        <span className="pw-spacer" />
        {workflow && <span className="pw-stat pw-stat--value" title="Value of the lines assigned to suppliers"><span>Assigned value</span><b>{pwRupees(workflow.assigned_value)}</b></span>}
        {workflow?.status && <span className={`pw-pill ${finalized || workflow.ready ? 'pw-pill--assigned' : 'pw-pill--pending'}`}>{String(workflow.status).replace(/_/g, ' ')}</span>}
        {view === 'qty' && totals.pending > 0 && (
          <button type="button" className="ow-btn ow-btn-sm" onClick={gotoNextPending} title="Jump to the next product not reviewed yet">Next pending →</button>
        )}
        {finalized
          ? <button type="button" className="pw-primary-btn pw-primary-btn--ghost" onClick={() => finalize(true)}>Reopen order</button>
          : <button type="button" className="pw-primary-btn" disabled={!workflow?.ready} title={workflow?.ready ? 'Lock this order' : 'Complete the review first'} onClick={() => finalize(false)}>Finalize order →</button>}
      </div>

      {record && store && (
        <DocumentCard kind={record.kind} store={record.store || store} row={record.row} productCode={record.productCode} session={session} onClose={() => setRecord(null)} />
      )}
    </section>
  );
}
