import { Fragment, useEffect, useMemo, useRef, useState } from 'react';
import { apiGet, apiPost } from '../../api/client.js';
import { listStores as directoryListStores } from '../../services/directoryService.js';
import {
  syncStoreIndex,
  upsertProducts,
  loadScope,
  filterProducts,
  getLastSync,
} from '../../../../supplier-stock-client/src/lib/productIndexCache.js';
import {
  applySyncResult,
  buildSynchronizedMap,
  emptySelectionState,
  selectionFor as selectionForStore,
  selectionStateForClick,
} from '../../../../supplier-stock-client/src/state/productSelection.js';
import { SalesSummaryGrid } from '@web/pages/quick-stock/SalesSummaryGrid.tsx';
import { BillDetailsModal } from '../../components/BillDetailsModal.jsx';
import './storeClientStockEnquiry.css';

// Verbatim Store Client Stock Enquiry (desktop/supplier-stock-client/src/App.jsx
// StockVerticalView + StoreComparisonMatrix). The only adaptation is the api
// object below, which calls this app's authenticated client with the workspace
// tenant. Search, matching, and calculations are unchanged.

let boundTenantId = '';

export function bindStockEnquiryTenant(tenantId) {
  boundTenantId = tenantId || '';
}

function tenantOf(filters) {
  return filters?.tenantId || boundTenantId;
}

function asArray(value) {
  if (Array.isArray(value)) return value;
  if (Array.isArray(value?.items)) return value.items;
  if (Array.isArray(value?.data)) return value.data;
  return [];
}

const api = {
  listStores() {
    return directoryListStores();
  },
  getProductIndex(_session, filters = {}) {
    const params = new URLSearchParams({ tenant_id: tenantOf(filters) });
    if (filters.storeId) params.set('store_id', filters.storeId);
    return apiGet(`/api/stock-availability/products/index?${params.toString()}`);
  },
  searchStockProducts(query, _session, filters = {}) {
    const params = new URLSearchParams({
      tenant_id: tenantOf(filters),
      q: query,
      only_stock: filters.onlyStock ? '1' : '0',
    });
    return apiGet(`/api/stock-availability/products/search?${params.toString()}`);
  },
  searchStockBatches(query, _session, filters = {}) {
    const params = new URLSearchParams({
      tenant_id: tenantOf(filters),
      batch: query?.batch || '',
      mrp: query?.mrp || '',
      product: query?.product || '',
    });
    return apiGet(`/api/stock-availability/batches/search?${params.toString()}`);
  },
  getStockCore(storeId, productCode, _session, filters = {}) {
    const params = new URLSearchParams({
      tenant_id: tenantOf(filters),
      store_id: storeId,
      product: productCode,
      months: String(filters.months || 3),
    });
    return apiGet(`/api/stock-availability/products/core?${params.toString()}`);
  },
  syncStockSelection(sourceStoreId, sourceProductCode, sourceProductName, targetStoreIds, _session, filters = {}) {
    return apiPost('/api/stock-availability/products/sync-selection', {
      tenant_id: tenantOf(filters),
      source_store_id: sourceStoreId,
      source_product_code: sourceProductCode,
      source_product_name: sourceProductName,
      target_store_ids: targetStoreIds || [],
    });
  },
  getBillItems(storeId, billNo, billDate, _session, filters = {}) {
    const params = new URLSearchParams({
      tenant_id: tenantOf(filters),
      store_id: storeId,
      bill_no: billNo,
    });
    if (billDate) params.set('bill_date', String(billDate).slice(0, 10));
    return apiGet(`/api/stock-availability/products/bill?${params.toString()}`);
  },
};

const DEFAULT_STOCK_FIELDS = {
  trend: { purchase: true, sales: true, stock: true },
};

function makeConcurrencyLimiter(limit) {
  let active = 0;
  const queue = [];
  const next = () => {
    if (active >= limit || !queue.length) return;
    active += 1;
    const { fn, resolve, reject } = queue.shift();
    fn().then(resolve, reject).finally(() => { active -= 1; next(); });
  };
  return (fn) => new Promise((resolve, reject) => { queue.push({ fn, resolve, reject }); next(); });
}

// Stock Availability / Network Stock product-detail cache (batches, purchase
// history, sales history, monthly trend) was cached forever by storeId:
// productCode with no expiry -- a product panel opened once stayed on that
// exact snapshot for the rest of the session, so a purchase/sale posted
// afterward (live data -- these screens stay open for hours during a working
// day) never showed up without the operator knowing to force-reload the whole
// app. A short TTL keeps the instant re-open feel for a few minutes of
// back-and-forth navigation while still catching up on real new transactions.
const STOCK_CORE_CACHE_TTL_MS = 3 * 60 * 1000;
function isStockCoreFresh(entry) {
  return Boolean(entry) && (Date.now() - (entry.fetchedAt || 0)) < STOCK_CORE_CACHE_TTL_MS;
}

function canViewPurchaseDetails(session) {
  const roles = session?.user?.roles || [];
  const roleNames = roles.map((role) => String(role?.role_name || role?.role || '').toLowerCase());
  return roleNames.some((name) => name.includes('purchase'));
}

function isSalesmanOnly(session) {
  const roles = session?.user?.roles || [];
  const roleNames = roles.map((role) => String(role?.role_name || role?.role || '').toLowerCase());
  if (!roleNames.length) return false;
  return roleNames.every((name) => name.includes('salesman') || name.includes('sales man'));
}

function isSuperAdmin(session) {
  // Mirrors backend dependencies.auth.has_full_access: a platform user (no
  // store-scoped role at all, e.g. superadmin with tenant_id=NULL) is always
  // full-access. Role names are also compared with separators stripped so
  // 'SUPER_ADMIN', 'Super Admin', and 'superadmin' all match — a plain
  // includes('super admin') missed the underscore variant used by this seed.
  if (session?.user?.is_platform_user) return true;
  const roles = session?.user?.roles || [];
  const roleNames = roles.map((role) => String(role?.role_name || role?.role || '').toLowerCase().replace(/[^a-z]/g, ''));
  return roleNames.some((name) => name.includes('superadmin') || name.includes('platformowner'));
}

function canUnlockDeviceSetup(userOrSession) {
  const roles = userOrSession?.user?.roles || userOrSession?.roles || [];
  const roleNames = roles.map((role) => String(role?.role_name || role?.role || '').toLowerCase());
  return roleNames.some((name) => (
    name.includes('admin')
    || name.includes('purchase_manager')
    || name.includes('purchase manager')
    || name.includes('platform_owner')
    || name.includes('platform owner')
  ));
}

function isWarehouseStore(store) {
  return String(store?.store_code || '').trim().toUpperCase() === 'NMW';
}

// Field-level visibility tier for Purchase/Billing History: NONE hides the
// section entirely, SUMMARY shows abbreviated/derived figures only, FULL
// shows every field (supplier name, PTR, customer, salesman...).
function historyVisibility(session) {
  if (isSalesmanOnly(session)) return 'NONE';
  if (isSuperAdmin(session) || canViewPurchaseDetails(session)) return 'FULL';
  return 'SUMMARY';
}

function abbreviateSupplierName(name, maxLength = 10) {
  const value = String(name || '').trim();
  if (!value) return '-';
  return value.length > maxLength ? `${value.slice(0, maxLength)}...` : value;
}

function formatMoney(value) {
  const num = Number(value);
  return Number.isFinite(num) ? num.toFixed(2) : '-';
}

function formatQty(value) {
  const num = Number(value);
  return Number.isFinite(num) ? String(num) : (value ?? '-');
}

function formatStamp12(ts) {
  return new Date(ts).toLocaleString('en-GB', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: 'numeric', minute: '2-digit', second: '2-digit', hour12: true,
  }).replace(/\b([ap])m\b/gi, (s) => s.toUpperCase());
}

const STORE_COLORS = ['#3b82f6', '#14b8a6', '#6366f1', '#0ea5e9', '#8b5cf6', '#06b6d4'];

const PURCHASE_METRIC_FIELDS = [
  ['grn_no', 'GRN No / Invoice No', 'text'],
  ['date', 'GRN Date / Invoice Date', 'date'],
  ['qty', 'Qty', 'qty'],
  ['free', 'Free', 'qty'],
  ['mrp', 'MRP', 'money'],
  ['ptr', 'PTR', 'money'],
  ['cost', 'Cost', 'money'],
  ['dis_pct', 'Dis%', 'text']
];
// Fields only a FULL-visibility user (super admin / purchase role) may see.
// The party block (supplier / source store) is also FULL-only.
const PURCHASE_FULL_ONLY_FIELDS = new Set(['dis_pct']);

function PurchaseDetailCard({ detail, onClose, visibility = 'SUMMARY' }) {
  const { store, row } = detail;
  // The backend resolves the party TYPE (internal store transfer vs external
  // supplier); the UI never guesses from the displayed name. Internal 'TI'
  // transfers surface the source store (e.g. NMW), NOT a supplier.
  const partyType = String(row.party_type || '').toLowerCase();
  const isTransfer = partyType === 'transfer';
  // 'via_warehouse': the store received this stock from the warehouse, so we
  // surface the warehouse's REAL supplier (e.g. PENTACARE) and note the source
  // store as a subtitle ("via NMW") rather than hiding it as a plain transfer.
  const isViaWarehouse = partyType === 'via_warehouse';
  const showParty = visibility === 'FULL';
  const partyLabel = isTransfer ? 'Source Store' : 'Supplier';
  const partyName = String(row.supplier || '').trim() || '-';
  const sourceStore = String(row.source_store_name || '').trim();
  const partySub = isTransfer ? (sourceStore || null)
    : isViaWarehouse ? (sourceStore ? `via ${sourceStore}` : null)
    : null;

  const metrics = PURCHASE_METRIC_FIELDS.filter(([key]) =>
    (visibility === 'FULL' || !PURCHASE_FULL_ONLY_FIELDS.has(key))
    && row[key] !== undefined && row[key] !== null && row[key] !== '');

  useEffect(() => {
    function closeOnEscape(event) {
      if (event.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [onClose]);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="purchase-detail-card purchase-detail-card--compact"
        role="dialog"
        aria-modal="true"
        aria-labelledby="purchase-detail-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="purchase-detail-header">
          <div className="purchase-detail-heading">
            <span className="purchase-detail-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24"><path d="M7 3h10v2h2a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h2V3Zm2 2h6V4H9v1ZM5 8v11h14V8H5Zm3 3h8v2H8v-2Zm0 4h5v2H8v-2Z" /></svg>
            </span>
            <div>
              <span className="purchase-detail-eyebrow">Purchase Record</span>
              <strong id="purchase-detail-title">
                {store.store_name || store.store_code}{row.grn_no ? ` • GRN #${row.grn_no}` : ''}
              </strong>
            </div>
          </div>
          <button type="button" className="purchase-detail-close" onClick={onClose} aria-label="Close purchase details">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m7.4 6 4.6 4.6L16.6 6 18 7.4 13.4 12l4.6 4.6-1.4 1.4-4.6-4.6L7.4 18 6 16.6l4.6-4.6L6 7.4 7.4 6Z" /></svg>
          </button>
        </div>
        <div className="purchase-detail-body">
          {showParty && (
            <div className={`purchase-party ${isTransfer ? 'purchase-party--transfer' : 'purchase-party--supplier'} ${isViaWarehouse ? 'purchase-party--via-warehouse' : ''}`}>
              <span className="purchase-party-label">{partyLabel}</span>
              <strong className="purchase-party-name" title={partyName}>{partyName}</strong>
              {partySub && <span className="purchase-party-sub" title={partySub}>{partySub}</span>}
            </div>
          )}
          <div className="purchase-metric-grid">
            {metrics.map(([key, label, type]) => (
              <div className="purchase-metric" key={key}>
                <span>{label}</span>
                <strong className={type === 'money' ? 'num-value' : ''}>
                  {type === 'date' ? formatDate(row[key])
                    : type === 'money' ? formatMoney(row[key])
                    : type === 'qty' ? formatQty(row[key])
                    : row[key]}
                </strong>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function BillDetailCard({ detail, session, visibility = 'SUMMARY', onClose }) {
  const { store, sale, product } = detail;
  const productName = presentText(product?.product_name);

  return (
    <BillDetailsModal
      storeLabel={store.store_code || storeLabel(store)}
      storeName={store.store_name}
      billNo={sale.bill_no}
      billDate={sale.date}
      customer={sale.customer}
      visibility={visibility}
      highlightProductName={productName}
      fetchItems={() => api.getBillItems(store.store_id, sale.bill_no, sale.date, session).then(asArray)}
      onClose={onClose}
    />
  );
}

function SkeletonBlock({ lines = 3 }) {
  return (
    <div className="skeleton-block">
      {Array.from({ length: lines }, (_, index) => <span key={index} className="skeleton-line" />)}
    </div>
  );
}

function shortStoreName(value) {
  return String(value || 'STORE').replace(/^Nathan\s+Medicals\s*/i, '').slice(0, 4).toUpperCase() || 'STORE';
}

function storeLabel(store) {
  if (store?.store_code) return store.store_code;
  const name = String(store?.store_name || '').replace(/^Nathan\s+Medicals\s*/i, '').trim();
  return name ? `NM${name.toUpperCase()}` : 'STORE';
}

function monthKey(value) {
  if (!value) return '';
  const raw = String(value).trim();
  const isoMatch = raw.match(/^(\d{4})-(\d{2})/);
  if (isoMatch) return `${isoMatch[1]}-${isoMatch[2]}`;
  const slashMatch = raw.match(/^(\d{1,2})\/(\d{1,2})\/(\d{2,4})$/);
  if (slashMatch) {
    const year = slashMatch[3].length === 2 ? `20${slashMatch[3]}` : slashMatch[3];
    return `${year}-${slashMatch[2].padStart(2, '0')}`;
  }
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return '';
  return `${parsed.getFullYear()}-${String(parsed.getMonth() + 1).padStart(2, '0')}`;
}

function buildChartRows(rows, purchases = [], sales = []) {
  const movementRows = Array.isArray(rows) ? rows : [];
  const orderedKeys = [];
  const byMonth = new Map();
  const ensureMonth = (key) => {
    if (!key) return null;
    if (!byMonth.has(key)) {
      orderedKeys.push(key);
      byMonth.set(key, { period: key, pur: 0, tin: 0, sal: 0, tout: 0, stk: 0 });
    }
    return byMonth.get(key);
  };

  movementRows.forEach((row) => {
    const key = monthKey(row.period || row.month);
    if (!key) return;
    ensureMonth(key);
    byMonth.set(key, {
      period: key,
      pur: Number(row.pur || 0),
      tin: Number(row.tin || 0),
      sal: Number(row.sal || 0),
      tout: Number(row.tout || 0),
      stk: Number(row.stk || 0)
    });
  });

  if (!orderedKeys.length) {
    const base = new Date();
    base.setDate(1);
    for (let offset = 3; offset >= 0; offset -= 1) {
      const point = new Date(base.getFullYear(), base.getMonth() - offset, 1);
      const key = `${point.getFullYear()}-${String(point.getMonth() + 1).padStart(2, '0')}`;
      orderedKeys.push(key);
      byMonth.set(key, { period: key, pur: 0, tin: 0, sal: 0, tout: 0, stk: 0 });
    }
  }

  purchases.forEach((row) => {
    const key = monthKey(row.grndate || row.date);
    const target = ensureMonth(key);
    if (!target) return;
    if (!target.pur && !target.tin) {
      target.pur += Number(row.qty || 0) + Number(row.free || 0);
    }
  });

  sales.forEach((row) => {
    const key = monthKey(row.bill_date || row.date);
    const target = ensureMonth(key);
    if (!target) return;
    if (!target.sal && !target.tout) {
      target.sal += Number(row.qty || 0);
    }
  });

  orderedKeys.sort((a, b) => a.localeCompare(b));
  return orderedKeys.slice(-4).map((key) => byMonth.get(key));
}

// Tracks the rendered pixel size of the plot so the SVG viewBox maps ~1:1 to
// screen units (crisp text, no aspect distortion under preserveAspectRatio).
function useChartSize() {
  const ref = useRef(null);
  const [size, setSize] = useState({ w: 220, h: 120 });
  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const ro = new ResizeObserver((entries) => {
      const cr = entries[0].contentRect;
      setSize({ w: Math.max(140, cr.width), h: Math.max(80, cr.height) });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, size];
}

// Restyled to the web "regular model" (sa-chart): grouped bars over a tinted
// plot with gridlines + a Y-axis, value labels on each bar, a floating
// per-month tooltip and a focused-month readout row. Transfer in/out stay
// folded into Purchase/Sales to match the desktop data model + field toggles.
function MonthlyMovementChart({ rows, purchases = [], sales = [], visibleFields = DEFAULT_STOCK_FIELDS.trend, maxBarWidth }) {
  const months = buildChartRows(rows, purchases, sales);
  const [hover, setHover] = useState(null);
  const [tip, setTip] = useState({ x: 0, y: 0 });
  const [plotRef, { w: W, h: H }] = useChartSize();

  const series = [
    visibleFields.purchase && { key: 'pur', label: 'Purchase', short: 'PUR', color: '#2563eb', light: '#7db0ff', dark: '#1a3fae', value: (row) => Number(row.pur || 0) + Number(row.tin || 0) },
    visibleFields.sales && { key: 'sal', label: 'Sales', short: 'SAL', color: '#16a34a', light: '#67e08c', dark: '#12662f', value: (row) => Number(row.sal || 0) + Number(row.tout || 0) },
    visibleFields.stock && { key: 'stk', label: 'Stock', short: 'STK', color: '#dc2626', light: '#fb8686', dark: '#9c1414', value: (row) => Number(row.stk || 0) }
  ].filter(Boolean);

  if (!months.length || !series.length) return <div className="row-empty-state">No data</div>;

  const n = months.length || 1;
  const focus = hover ?? months.length - 1;
  const max = Math.max(1, ...months.flatMap((row) => series.map((s) => Math.abs(s.value(row)))));
  // Axis now shows the exact top-of-scale quantity (e.g. "10,900"), so the
  // left gutter widens to fit the longest tick label instead of a fixed 30px
  // that only ever had to hold a 4-char "10.9k".
  const axisTopLabel = exactQuantity(Math.round(max));
  const padL = Math.max(28, Math.min(54, axisTopLabel.length * 4.6 + 8));
  const padR = 8;
  const padT = 8;
  const padB = 15;
  const plotW = Math.max(30, W - padL - padR);
  const plotH = Math.max(30, H - padT - padB);
  const baseY = padT + plotH;

  const groupW = plotW / n;
  // Wider bars / tighter gaps for a bold, clear view (max usable bar width).
  const groupGap = Math.min(groupW * 0.14, 12);
  const rawInnerW = Math.max(series.length * 9, groupW - groupGap);
  const rawBarGap = Math.max(1, rawInnerW * 0.035);
  const rawBarW = (rawInnerW - rawBarGap * (series.length - 1)) / series.length;
  // maxBarWidth (opt-in, only passed by the Network Stock branch cards' more
  // compact chart panel): caps bar width instead of letting bars stretch to
  // fill all available groupW, and widens the gap with the reclaimed space
  // so month groups stay visually separated rather than touching.
  const barW = maxBarWidth ? Math.min(rawBarW, maxBarWidth) : rawBarW;
  const barGap = maxBarWidth && barW < rawBarW ? Math.max(rawBarGap, 6) : rawBarGap;
  const innerW = barW * series.length + barGap * (series.length - 1);

  // Value labels: when an exact quantity ("1,190") is wider than its bar slot,
  // adjacent labels in a month group overlapped into an unreadable smear. In
  // that case every other bar's label is lifted one text row, and the label
  // band above the bars reserves room for both rows. Must match the
  // .sa-chart__barval font-size in styles.css.
  const valFont = 9;
  const labelWidth = (value) => exactQuantity(value).length * valFont * 0.6;
  const crowded = series.length > 1 && months.some((row) => series.some((s) => labelWidth(s.value(row)) > barW + barGap));
  const labelRow = valFont + 1;
  const labelBand = Math.max(plotH * 0.12, crowded ? labelRow * 2 + 2 : labelRow + 2);
  const barAreaH = plotH - labelBand;
  const barTopLimit = padT + labelBand;

  return (
    <div className="sa-chart">
      <div
        className="sa-chart__plot"
        ref={plotRef}
        onMouseMove={(event) => setTip({ x: event.nativeEvent.offsetX, y: event.nativeEvent.offsetY })}
        onMouseLeave={() => setHover(null)}
      >
        <svg width="100%" height="100%" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Monthly movement chart" className="sa-chart__svg" preserveAspectRatio="xMinYMin meet">
          <defs>
            <linearGradient id="sa-chart-glass" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" className="sa-chart__glass-a" />
              <stop offset="100%" className="sa-chart__glass-b" />
            </linearGradient>
            {series.map((s) => (
              <linearGradient key={s.key} id={`sa-bar-${s.key}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={s.light} />
                <stop offset="48%" stopColor={s.color} />
                <stop offset="100%" stopColor={s.dark} />
              </linearGradient>
            ))}
          </defs>
          <rect className="sa-chart__plotbg" x={padL - 6} y={barTopLimit - 3} width={plotW + 14} height={barAreaH + 6} rx={8} fill="url(#sa-chart-glass)" />

          {[0, 0.5, 1].map((t) => {
            const y = baseY - t * barAreaH;
            return (
              <g key={t}>
                <line x1={padL} y1={y} x2={W - padR} y2={y} stroke="rgba(100,116,139,0.18)" strokeWidth={1} />
                <text x={padL - 5} y={y + 3} textAnchor="end" className="sa-chart__axis">{exactQuantity(Math.round(max * t))}</text>
              </g>
            );
          })}

          {months.map((row, i) => {
            const groupX = padL + i * groupW + (groupW - innerW) / 2;
            const focused = i === focus;
            return (
              <g key={row.period ?? i}>
                {series.map((s, j) => {
                  const value = s.value(row);
                  const h = (Math.abs(value) / max) * barAreaH;
                  const x = groupX + j * (barW + barGap);
                  const cx = x + barW / 2;
                  const top = baseY - h;
                  const lift = crowded && j % 2 === 1 ? labelRow : 0;
                  const labelY = Math.max(barTopLimit - 1, top - 3) - lift;
                  return (
                    <g key={s.key}>
                      <rect x={x} y={top} width={Math.max(4, barW)} height={h} rx={3} fill={`url(#sa-bar-${s.key})`}>
                        <title>{`${row.period ?? ''} · ${s.label}: ${exactQuantity(value)}`}</title>
                      </rect>
                      {/* glossy highlight down the left edge of each bar */}
                      {h > 4 && (
                        <rect x={x + 1} y={top + 1} width={Math.max(1, Math.min(2.5, barW * 0.22))} height={Math.max(0, h - 2)} rx={1.5} fill="rgba(255,255,255,0.38)" />
                      )}
                      {value > 0 && (
                        <text x={cx} y={labelY} textAnchor="middle" className={`sa-chart__barval sa-chart__barval--${s.key}`}>{exactQuantity(value)}</text>
                      )}
                    </g>
                  );
                })}
                <rect
                  x={groupX - barGap}
                  y={barTopLimit}
                  width={innerW + barGap * 2}
                  height={barAreaH}
                  fill="transparent"
                  rx={6}
                  onMouseEnter={() => setHover(i)}
                  onMouseLeave={() => setHover(null)}
                />
                <text x={groupX + innerW / 2} y={H - 4} textAnchor="middle" className={`sa-chart__month${focused ? ' sa-chart__month--on' : ''}`}>{row.period ?? ''}</text>
              </g>
            );
          })}
        </svg>

        {hover != null && months[hover] && (
          <div
            className="sa-chart__tip"
            style={{ left: Math.min(Math.max(tip.x + 10, 4), Math.max(4, W - 130)), top: Math.max(tip.y - 6, 4) }}
            role="tooltip"
          >
            <div className="sa-chart__tip-head">{months[hover].period ?? ''}</div>
            {series.map((s) => (
              <div className="sa-chart__tip-row" key={s.key}>
                <span className="sa-chart__tip-key"><span className="sa-chart__swatch" style={{ background: s.color }} />{s.label}</span>
                <span className="sa-chart__tip-val">{exactQuantity(s.value(months[hover]))}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function exactQuantity(value) {
  const number = Number(value) || 0;
  return Number.isInteger(number)
    ? number.toLocaleString('en-US')
    : number.toLocaleString('en-US', { maximumFractionDigits: 2 });
}

function formatDate(value) {
  if (!value) return '-';
  const raw = String(value).slice(0, 10);
  const parts = raw.split('-');
  if (parts.length === 3) return `${parts[2]}/${parts[1]}/${parts[0].slice(2)}`;
  return raw;
}

const SALES_MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** Sales grid dates match Quick Stock (`02-Oct-26`) using the same calendar
 *  parts formatDate already reads. No Date parse, so the day does not shift. */
function formatSalesDate(value) {
  if (!value) return '—';
  const raw = String(value).slice(0, 10);
  const parts = raw.split('-');
  if (parts.length === 3 && parts[0].length === 4) {
    const month = SALES_MONTHS[Number(parts[1]) - 1];
    const day = parts[2].padStart(2, '0');
    if (month && /^\d{2}$/.test(day)) return `${day}-${month}-${parts[0].slice(-2)}`;
  }
  return formatDate(value);
}

function presentText(value) {
  if (value == null) return '';
  const text = String(value).trim();
  if (!text || text === '-' || text === '—') return '';
  return text;
}

function existingSaleRate(row) {
  if (!row || typeof row !== 'object') return null;
  for (const key of ['sale_rate', 'saleRate', 'selling_rate', 'sellingRate']) {
    const value = row[key];
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    const text = presentText(value);
    if (text) return text;
  }
  return null;
}

function formatMonthYear(value) {
  if (!value) return '-';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return formatDate(value);
  const mon = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][d.getMonth()];
  return `${mon}/${String(d.getFullYear()).slice(-2)}`;
}

function SvbMiniTable({ head, rows, emptyMessage, raw, onRowClick }) {
  if (!rows.length) return <div className="ns-card__waiting">{emptyMessage}</div>;
  return (
    <table className="ns-mini-table svb-sec__table">
      <thead>
        <tr>{head.map((col, i) => <th key={i} className={col.num ? 'num-col' : undefined}>{col.label}</th>)}</tr>
      </thead>
      <tbody>
        {rows.map((cells, r) => (
          <tr
            key={r}
            className={onRowClick ? 'is-clickable' : undefined}
            onClick={onRowClick ? () => onRowClick(raw?.[r]) : undefined}
          >
            {cells.map((cell, i) => {
              const cls = [head[i]?.num ? 'num-col' : null, head[i]?.cls || null].filter(Boolean).join(' ') || undefined;
              const tip = cell == null || cell === '' ? undefined : String(cell);
              return <td key={i} className={cls} title={tip}>{cell}</td>;
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// Per-store detail renderers for one matrix cell. `core` is that store's
// selected product's { batches, purchases, sales, movement } (column aliases
// from stock.usp_ProductCore). Each returns the cell body for its info row.
// Clicking a chart / purchase / sales opens a reusable detail card (Esc closes).
function svbChartCell(core, onOpen) {
  const movement = asArray(core?.movement);
  const purchases = asArray(core?.purchases);
  const sales = asArray(core?.sales);
  if (!(movement.length || purchases.length || sales.length)) return <div className="ns-card__waiting">No chart data.</div>;
  return (
    <div className="scm-chart scm-chart--click" onClick={onOpen} title="Click to enlarge">
      <MonthlyMovementChart rows={movement} purchases={purchases} sales={sales} maxBarWidth={14} />
    </div>
  );
}
function svbBatchCell(core) {
  const all = asArray(core?.batches);
  // Show EVERY in-stock batch; if the product is fully out of stock, fall back
  // to the 5 most recently purchased batches for reference (owner request).
  const inStock = all.filter((b) => Number(b.stock) > 0);
  const list = inStock.length
    ? inStock
    : [...all].sort((a, b) => new Date(b.last_purchase_date || 0) - new Date(a.last_purchase_date || 0)).slice(0, 5);
  return (
    <SvbMiniTable
      head={[{ label: 'Exp' }, { label: 'Stk', num: true }, { label: 'MRP', num: true }, { label: 'S.Unt', num: true }, { label: 'P.Age', num: true }, { label: 'S.Age', num: true }]}
      rows={list.slice(0, 50).map((row) => [
        formatMonthYear(row.expiry_date), formatQty(row.stock), formatMoney(row.mrp), row.sale_unit ?? '-',
        row.purchase_age_days ?? '-', row.sales_age_days ?? '-',
      ])}
      emptyMessage="No batch data."
    />
  );
}
function purchaseBatch(row) {
  const value = row?.batch_no || row?.batchcode || row?.batch || '';
  return String(value).trim();
}

function svbPurchaseCell(core, onRowClick) {
  const rows = asArray(core?.purchases).slice(0, 40);
  const showBatch = rows.some((row) => purchaseBatch(row));
  const head = [
    { label: 'Date' },
    { label: 'GRN' },
    { label: 'Qty', num: true },
    { label: 'Free', num: true },
    { label: 'PTR', num: true },
    { label: 'MRP', num: true },
    { label: 'Supplier' },
  ];
  if (showBatch) head.push({ label: 'Batch' });
  return (
    <SvbMiniTable
      head={head}
      rows={rows.map((row) => {
        const cells = [
          formatDate(row.date),
          row.grn_no || '—',
          formatQty(row.qty),
          formatQty(row.free),
          formatMoney(row.ptr ?? row.cost),
          formatMoney(row.mrp),
          row.supplier || '—',
        ];
        if (showBatch) cells.push(purchaseBatch(row) || '—');
        return cells;
      })}
      raw={rows}
      onRowClick={onRowClick}
      emptyMessage="No purchase history."
    />
  );
}
function svbSalesCell(core, store, onRowClick, selectedKey) {
  const rows = asArray(core?.sales).slice(0, 40);
  if (!rows.length) return <div className="ns-card__waiting">No sales history.</div>;
  const view = rows.map((row, index) => ({
    key: `${store.store_id}|${index}|${row.date || ''}|${row.bill_no || ''}|${row.qty ?? ''}`,
    date: formatSalesDate(row.date),
    qty: formatQty(row.qty),
    customer: String(row.customer || '').trim(),
  }));
  return (
    <SalesSummaryGrid
      ariaLabel={`${storeLabel(store)} sales`}
      rows={view}
      selectedKey={selectedKey || null}
      onSelect={(key) => {
        const hit = view.findIndex((item) => item.key === key);
        if (hit >= 0) onRowClick?.(rows[hit], key);
      }}
    />
  );
}

// ── Store Comparison Matrix ────────────────────────────────────────────────
// Transposed layout: STORES are COLUMNS (across the top), INFORMATION TYPES are
// ROWS (down the left). One CSS-grid lays out a sticky row-label column + a
// sticky store-header row + the cells, so every cell in a row shares the row's
// height and columns line up perfectly. Each store column reads as a continuous
// vertical store card: Store Grid → Chart → Batch → Purchase → Sales.
//
// Per-store product selection + core cache are lifted HERE (not inside a cell)
// because clicking a product in a store's Store Grid cell must drive that same
// store's Chart/Batch/Purchase/Sales cells, which live in different grid rows.
const SCM_ROWS = [
  { key: 'grid', label: 'Store Grid', icon: 'workspace' },
  { key: 'chart', label: 'Chart', icon: 'chart' },
  { key: 'batch', label: 'Batch', icon: 'tags' },
  { key: 'purchase', label: 'Purchase', icon: 'procurement' },
  { key: 'sales', label: 'Sales', icon: 'reports' },
];

// Quick Stock: the same comparison model, fewer rows. No Batch row at all;
// Purchase/Sales are collapsed into ONE row with a toggle switch instead of
// two always-on rows (owner ruling: "reduce rows only remove batches and
// purchase and sales / purchase switch add").
const SCM_ROWS_COMPACT = [
  { key: 'grid', label: 'Store Grid' },
  { key: 'chart', label: 'Chart' },
  { key: 'sales_or_purchase', label: 'Sales / Purchase' },
];

// A single big label/value tile — used for the NMW warehouse summary a store
// user sees in place of the full (HO-only) tables.
function NmwTile({ label, value, hint, zero }) {
  return (
    <div className="scm-nmw">
      <span className="scm-nmw__label">{label}</span>
      <span className={`scm-nmw__value${zero ? ' scm-zero' : ''}`}>{value}</span>
      {hint && <span className="scm-nmw__hint">{hint}</span>}
    </div>
  );
}

function StoreComparisonMatrix({ stores, storeDetails, selectionFor, onProductSelect, superAdmin, session, rows = SCM_ROWS, notice = '', loadingStores = false }) {
  const [billDetail, setBillDetail] = useState(null);         // { store, sale }
  const [purchaseDetail, setPurchaseDetail] = useState(null); // { store, row }
  const [chartModal, setChartModal] = useState(null);         // { store, core }
  // Quick Stock's combined row only: which of Sales/Purchase the toggle shows.
  // One switch for the whole matrix (not per-store) — matches "switch add"
  // from the owner ruling, a single control rather than N per-column toggles.
  const [salesPurchaseMode, setSalesPurchaseMode] = useState('sales');
  const visibility = historyVisibility(session);

  // Esc closes any open detail / chart card and returns to the matrix.
  useEffect(() => {
    if (!billDetail && !purchaseDetail && !chartModal) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') { setBillDetail(null); setPurchaseDetail(null); setChartModal(null); } };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [billDetail, purchaseDetail, chartModal]);

  // The product selected in a store = its GREEN source (the column the user
  // clicked) OR its synchronized match (the same product auto-resolved here).
  function selectedCode(store) {
    const sel = selectionFor(store.store_id);
    return sel.sourceProductCode || sel.syncProductCode || null;
  }
  function storeCore(store) {
    const code = selectedCode(store);
    if (!code) return null;
    const core = storeDetails[store.store_id];
    return core && core.product?.product_code === code ? core : null;
  }

  // Store Grid (stock list) visible for EVERY store incl. NMW. MRP dropped so
  // the product name gets full width; a zero stock is flagged red; the selected
  // row (source or synced) is auto-scrolled into view so it's never hidden
  // below the fold in a column where it sits far down the list.
  function gridCell(store) {
    const products = asArray(store.products);
    const sel = selectionFor(store.store_id);
    const code = sel.sourceProductCode || sel.syncProductCode || null;
    const isSource = sel.sourceProductCode != null;
    return (
      <table className="ns-mini-table svb-sec__table svb-prod-table">
        <thead><tr><th>Product</th><th>Unit</th><th className="num-col">Stock</th></tr></thead>
        <tbody>
          {products.length === 0 ? (
            <tr className="scm-row-empty"><td colSpan={3}>—</td></tr>
          ) : products.map((p) => {
            const isSel = p.product_code === code;
            const cls = isSel ? (isSource ? 'is-source' : 'is-synced') : undefined;
            const stock = p.stock ?? p.total_stock ?? 0;
            return (
              <tr
                key={p.product_code}
                className={cls}
                onClick={() => onProductSelect(store, p)}
                ref={isSel ? (el) => { if (el) el.scrollIntoView({ block: 'nearest' }); } : undefined}
              >
                <td title={p.product_name}>{p.product_name || '-'}</td>
                <td title={p.sale_unit || p.unit_description || ''}>{p.sale_unit || p.unit_description || '-'}</td>
                <td className={`num-col scm-qty${Number(stock) === 0 ? ' scm-zero' : ''}`} title={formatQty(stock)}>{formatQty(stock)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    );
  }

  function detailCell(store, rowKey, isWarehouse) {
    const code = selectedCode(store);
    if (!code) return null;
    const core = storeCore(store);

    // NMW for a store user: the chart like every other store (owner ruling
    // 2026-10-26: "view all charts, only restrict NMW product details"), but
    // not the full batch/purchase/sales tables (HO-only) -- a useful summary of
    // the selected product in the warehouse instead: Expiry / PTR / MRP.
    if (isWarehouse && !superAdmin) {
      const product = asArray(store.products).find((p) => p.product_code === code);
      if (!core) return <div className="ns-card__waiting">Loading…</div>;
      if (rowKey === 'chart') return svbChartCell(core, () => setChartModal({ store, core }));
      const batches = asArray(core.batches);
      const ref = batches.find((b) => Number(b.stock) > 0) || batches[0]; // FEFO: in-stock, earliest expiry first
      if (rowKey === 'batch') return <NmwTile label="Nearest expiry" value={ref ? formatMonthYear(ref.expiry_date) : '—'} />;
      if (rowKey === 'purchase') return <NmwTile label="PTR" value={ref ? formatMoney(ref.ptr) : '—'} />;
      if (rowKey === 'sales') {
        const mrp = product?.mrp ?? ref?.mrp;
        return <NmwTile label="MRP" value={mrp != null ? formatMoney(mrp) : '—'} />;
      }
      if (rowKey === 'sales_or_purchase') {
        return salesPurchaseMode === 'purchase'
          ? <NmwTile label="PTR" value={ref ? formatMoney(ref.ptr) : '—'} />
          : <NmwTile label="MRP" value={(product?.mrp ?? ref?.mrp) != null ? formatMoney(product?.mrp ?? ref?.mrp) : '—'} />;
      }
      return null;
    }

    if (!core) return <div className="ns-card__waiting">Loading…</div>;
    const openSale = (row, key) => {
      if (!row) return;
      const product = asArray(store.products).find((item) => item.product_code === code) || core.product || null;
      setBillDetail({ store, sale: row, product, key });
    };
    const selectedKey = billDetail?.store?.store_id === store.store_id ? billDetail.key : null;
    if (rowKey === 'chart') return svbChartCell(core, () => setChartModal({ store, core }));
    if (rowKey === 'batch') return svbBatchCell(core);
    if (rowKey === 'purchase') return svbPurchaseCell(core, (row) => { if (row) setPurchaseDetail({ store, row }); });
    if (rowKey === 'sales') return svbSalesCell(core, store, openSale, selectedKey);
    if (rowKey === 'sales_or_purchase') {
      return salesPurchaseMode === 'purchase'
        ? svbPurchaseCell(core, (row) => { if (row) setPurchaseDetail({ store, row }); })
        : svbSalesCell(core, store, openSale, selectedKey);
    }
    return null;
  }

  // Single unified CSS grid (rail column + N store columns, header row + one
  // row per `rows` entry) instead of one independent grid per section — this
  // is the one-scroll-surface model from this directory's StockMatrixView.jsx
  // (Quick Stock), ported here so Batch/Purchase/Sales never end up behind
  // six separate per-cell scrollbars (owner: "always render the full grid,
  // avoid nested scrollbars"). This intentionally diverges this file's full
  // (SCM_ROWS) rendering path from the supplier-stock-client source it was
  // otherwise kept verbatim with (see the file's top comment) — do not
  // blindly re-sync this section from there.
  const compactMode = rows !== SCM_ROWS;
  const columnTemplate = `var(--scm-rail-w, 28px) repeat(${Math.max(stores.length, 1)}, minmax(220px, 1fr))`;
  const rowTemplate = compactMode
    ? 'auto minmax(140px,1fr) minmax(130px,1fr) minmax(110px,1fr)'
    : 'auto 180px 165px 165px minmax(130px,1fr) minmax(130px,1fr)';

  return (
    <div className="scm-scroll">
      <div
        className={`scm-grid${compactMode ? ' scm-grid--compact' : ''}`}
        style={{ gridTemplateColumns: columnTemplate, gridTemplateRows: rowTemplate }}
      >
        {loadingStores && (
          <div className="scm-loading-notice" style={{ gridRow: 1, gridColumn: 2 }}>Loading stores…</div>
        )}
        <div className="scm-corner" style={{ gridRow: 1, gridColumn: 1 }} />
        {stores.map((store, index) => {
          const color = STORE_COLORS[index % STORE_COLORS.length];
          const isWarehouse = isWarehouseStore(store);
          const code = selectedCode(store);
          const loading = code && !storeCore(store);
          return (
            <div
              className="scm-colhead"
              key={store.store_id}
              style={{ '--store-color': color, gridRow: 1, gridColumn: index + 2 }}
            >
              <span className="scm-colhead__code">{storeLabel(store)}</span>
              <span className="scm-colhead__name" title={store.store_name || ''}>{store.store_name || ''}</span>
              {isWarehouse && <span className="scm-wh">WH</span>}
              {loading && <span className="scm-colhead__loading" aria-label="Loading">…</span>}
            </div>
          );
        })}

        {rows.map((row, rowIndex) => {
          const colorRowKey = row.key === 'sales_or_purchase' ? salesPurchaseMode : row.key;
          const gridRow = rowIndex + 2;
          return (
            <Fragment key={row.key}>
              <div
                className={`scm-rowlabel scm-rowlabel--${colorRowKey}`}
                style={{ gridRow, gridColumn: 1 }}
              >
                {row.key === 'sales_or_purchase' ? (
                  <div className="scm-sp-toggle" role="tablist" aria-label="Sales or Purchase">
                    <button
                      type="button"
                      role="tab"
                      aria-selected={salesPurchaseMode === 'sales'}
                      className={salesPurchaseMode === 'sales' ? 'active' : ''}
                      onClick={() => setSalesPurchaseMode('sales')}
                    >
                      Sales
                    </button>
                    <button
                      type="button"
                      role="tab"
                      aria-selected={salesPurchaseMode === 'purchase'}
                      className={salesPurchaseMode === 'purchase' ? 'active' : ''}
                      onClick={() => setSalesPurchaseMode('purchase')}
                    >
                      Purchase
                    </button>
                  </div>
                ) : (
                  <span>{row.label}</span>
                )}
              </div>
              {stores.map((store, index) => {
                const color = STORE_COLORS[index % STORE_COLORS.length];
                const isWarehouse = isWarehouseStore(store);
                return (
                  <div
                    className={`scm-cell scm-cell--${colorRowKey}`}
                    key={`${row.key}-${store.store_id}`}
                    style={{ '--store-color': color, gridRow, gridColumn: index + 2 }}
                  >
                    {row.key === 'grid' ? gridCell(store) : detailCell(store, row.key, isWarehouse)}
                  </div>
                );
              })}
            </Fragment>
          );
        })}
      </div>

      {billDetail && (
        <BillDetailCard detail={billDetail} session={session} visibility={visibility} onClose={() => setBillDetail(null)} />
      )}
      {purchaseDetail && (
        <PurchaseDetailCard detail={purchaseDetail} visibility={visibility} onClose={() => setPurchaseDetail(null)} />
      )}
      {chartModal && (
        <div className="modal-overlay" onClick={() => setChartModal(null)}>
          <div className="scm-chart-modal" onClick={(e) => e.stopPropagation()}>
            <div className="scm-chart-modal__head">
              <strong>{(chartModal.store.store_name || storeLabel(chartModal.store))} — {chartModal.core.product?.product_name || 'Sales trend'}</strong>
              <button type="button" className="ghost-button" onClick={() => setChartModal(null)}>Close (Esc)</button>
            </div>
            <div className="scm-chart-modal__body">
              <MonthlyMovementChart rows={asArray(chartModal.core.movement)} purchases={asArray(chartModal.core.purchases)} sales={asArray(chartModal.core.sales)} maxBarWidth={30} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function StockVerticalView({ session, settings, compact = false, embedded = false, title = '' }) {
  const tenantId = settings?.tenantId || session?.user?.tenant_id || '';
  bindStockEnquiryTenant(tenantId);
  const nativeStoreId = session?.user?.roles?.[0]?.store_id || '';
  const superAdmin = isSuperAdmin(session);
  const [query, setQuery] = useState('');
  const [searchMode, setSearchMode] = useState('product');
  const [batchNo, setBatchNo] = useState('');
  const [batchMrp, setBatchMrp] = useState('');
  const [batchProduct, setBatchProduct] = useState('');
  const [onlyStock, setOnlyStock] = useState(false);
  const [stores, setStores] = useState([]);
  // storeId -> loaded core ({product,batches,purchases,sales,movement}) for the
  // ONE common selected product in that store.
  const [storeDetails, setStoreDetails] = useState({});
  // Two-colour cross-store selection (GREEN source + BLUE synchronized matches)
  // — the SAME model/state the main Stock Availability screen uses, so a product
  // clicked in ANY column selects the equivalent product in every other store.
  const [selectionState, setSelectionState] = useState(emptySelectionState);
  const [status, setStatus] = useState({ state: 'idle', message: 'Type at least 2 characters to search.' });
  // Offline / permanent-cache state (mirrors the horizontal Stock Availability
  // screen). When a search can't reach HO we serve the permanent LOCAL product
  // index (lib/productIndexCache.js) — an on-disk IndexedDB that SURVIVES a
  // system restart / logoff — so product names + last-known stock still render,
  // stamped with a "Last sync" time. Detail panels (batch/purchase/sales/chart)
  // need HO, so they stay blank offline.
  const [offline, setOffline] = useState(false);
  const [lastSync, setLastSync] = useState(null);
  // Store list for the offline scan — seeded from the SAME on-disk cache key the
  // horizontal screen writes, and refreshed from HO whenever reachable.
  const [allStores, setAllStores] = useState(() => {
    try { return JSON.parse(localStorage.getItem('nexora.desktop.storesCache') || '[]'); } catch { return []; }
  });
  const searchIdRef = useRef(0);
  const offlineIndexRef = useRef(new Map());
  const detailCacheRef = useRef(new Map());   // storeId:product_code -> core
  const syncTicketRef = useRef(0);            // drops out-of-order sync responses
  // Selecting a product fans out to every matched store's core at once (6+ for
  // a common product) -- cap how many of those hit the backend simultaneously
  // (see makeConcurrencyLimiter's comment for why).
  const coreLimitRef = useRef(makeConcurrencyLimiter(4));

  const tenantStores = useMemo(() => {
    if (!tenantId) return allStores;
    return allStores.filter((store) => String(store?.tenant_id || '') === String(tenantId));
  }, [allStores, tenantId]);

  const searchProductsByStore = useMemo(
    () => new Map(stores.map((s) => [s.store_id, s.products || []])),
    [stores]
  );

  // Keep the store list fresh when HO is reachable (shared cache key with the
  // horizontal screen) so the offline scan below knows every store.
  useEffect(() => {
    api.listStores(session).then((rows) => {
      const items = asArray(rows);
      setAllStores(items);
      try { localStorage.setItem('nexora.desktop.storesCache', JSON.stringify(items)); } catch { /* best effort */ }
    }).catch(() => { /* offline: keep the cached store list */ });
  }, [session]);

  // Show the last cache timestamp as soon as the screen mounts (before any
  // refresh), so an offline launch still reports how fresh the data is.
  useEffect(() => {
    let cancelled = false;
    getLastSync(tenantId).then((ts) => { if (!cancelled) setLastSync(ts); });
    return () => { cancelled = true; };
  }, [tenantId]);

  // Seed + keep fresh the PERMANENT on-disk product index so this screen works
  // offline even if the horizontal screen was never opened. Fail-soft and light
  // (10-min interval) — identical to the horizontal screen's seeder, and writing
  // the same IndexedDB so the two screens share one cache.
  useEffect(() => {
    if (!tenantId || !session) return undefined;
    let cancelled = false;
    async function refreshIndex() {
      try {
        const resp = await api.getProductIndex(session, { tenantId });
        if (cancelled) return;
        for (const store of asArray(resp?.stores)) {
          await syncStoreIndex(tenantId, store.store_id,
            { store_code: store.store_code, store_name: store.store_name },
            asArray(store.products));
        }
        if (!cancelled) {
          offlineIndexRef.current.clear(); // cache changed — drop stale in-memory scopes
          setLastSync(Date.now());
          setOffline(false);
        }
      } catch { /* offline / HO down: keep serving the existing cache */ }
    }
    refreshIndex();
    const timer = setInterval(refreshIndex, 15 * 60 * 1000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [session, tenantId]);

  function formatSyncTime(ts) {
    if (!ts) return 'never';
    try { return formatStamp12(ts); } catch { return 'unknown'; }
  }

  // Build the per-store search shape entirely from the permanent local index —
  // used when HO is unreachable. Scopes are loaded once into offlineIndexRef
  // then filtered in memory (instant on later keystrokes).
  async function buildOfflineStores(value) {
    const out = [];
    for (const store of tenantStores) {
      let list = offlineIndexRef.current.get(store.store_id);
      if (!list) {
        list = await loadScope(tenantId, store.store_id);
        offlineIndexRef.current.set(store.store_id, list);
      }
      // Offline index is matched by substring (already "contains"), so the
      // wildcard chars are stripped — "*karma" / "%karma" -> "karma".
      let matches = filterProducts(list, value.replace(/[%*]/g, ''), 50);
      if (onlyStock) matches = matches.filter((p) => Number(p.stock) > 0);
      if (matches.length) {
        out.push({
          store_id: store.store_id,
          store_code: store.store_code,
          store_name: store.store_name,
          is_warehouse: store.is_warehouse,
          tenant_id: store.tenant_id,
          products: matches.map((p) => ({
            product_code: p.product_code,
            product_name: p.product_name,
            sale_unit: p.unit,
            stock: p.stock,
            mrp: null,
            batch_no: null,
          })),
        });
      }
    }
    return out;
  }

  async function runSearch(value, batchQuery = null) {
    const searchId = ++searchIdRef.current;
    setStatus({ state: 'loading', message: batchQuery ? 'Searching batches…' : 'Searching products…' });
    let all;
    try {
      // '*' is the user-facing wildcard; the backend LIKE uses '%'. Translate so
      // "*karma" becomes a contains-search (ProductName LIKE '%karma%'). A literal
      // '%' the user types still works too.
      const likeTerm = value.replace(/\*/g, '%');
      const response = batchQuery
        ? await api.searchStockBatches(batchQuery, session, { tenantId })
        : await api.searchStockProducts(likeTerm, session, { onlyStock });
      if (searchIdRef.current !== searchId) return;
      if (offline) setOffline(false);
      all = asArray(response?.stores);
    } catch (netErr) {
      // OFFLINE / HO unreachable: serve the permanent local index so the
      // operator still gets product names + last-known stock from cache.
      // Batch/MRP search has no local index, so it stays an error.
      if (searchIdRef.current !== searchId) return;
      if (batchQuery) {
        setStores([]);
        setStoreDetails({});
        setSelectionState(emptySelectionState());
        setOffline(false);
        setStatus({ state: 'error', message: netErr?.message || 'Batch search needs the server.' });
        return;
      }
      const offlineStores = await buildOfflineStores(value);
      if (searchIdRef.current !== searchId) return;
      setOffline(true);
      const ts = await getLastSync(tenantId);
      setLastSync(ts);
      setStores(offlineStores);
      // Offline: pick the first store's top product as the common product and
      // exact-match it across cached stores (same product_code). Detail cores
      // are empty here — HO is needed for batch/purchase/sales/chart — so those
      // cells show their normal empty state, not a stuck spinner.
      const oFirst = offlineStores.find((s) => (s.products || [])[0]);
      if (oFirst) {
        const src = oFirst.products[0];
        const exact = [];
        offlineStores.forEach((s) => {
          if (s.store_id === oFirst.store_id) return;
          const m = (s.products || []).find((p) => p.product_code === src.product_code);
          if (m) exact.push({ store_id: s.store_id, product: { product_code: m.product_code, product_name: m.product_name, mrp: m.mrp }, match_type: 'EXACT_PRODUCT_CODE', score: 100 });
        });
        setSelectionState(applySyncResult(selectionStateForClick(oFirst.store_id, src.product_code), oFirst.store_id, src.product_code, buildSynchronizedMap(exact)));
        const seeded = { [oFirst.store_id]: { product: src, batches: [], purchases: [], sales: [], movement: [] } };
        exact.forEach((e) => { seeded[e.store_id] = { product: e.product, batches: [], purchases: [], sales: [], movement: [] }; });
        setStoreDetails(seeded);
      } else {
        setSelectionState(emptySelectionState());
        setStoreDetails({});
      }
      const oTotal = offlineStores.reduce((sum, s) => sum + (s.products || []).length, 0);
      setStatus({
        state: oTotal ? 'ok' : 'idle',
        message: oTotal
          ? `Offline — ${oTotal} cached match(es). Last sync ${formatSyncTime(ts)}.`
          : `Offline — no cached match. Last sync ${formatSyncTime(ts)}.`,
      });
      return;
    }

    // New result set → reset the common selection + loaded detail. The
    // auto-select effect then picks the first product as the shared context and
    // the cross-store matcher loads each store's core for it.
    setStores(all);
    setStoreDetails({});
    setSelectionState(emptySelectionState());

    // Grow the on-disk cache + refresh the "last sync" stamp from these live
    // results. This keeps the global Last-sync badge and offline search working
    // even on backends that don't expose the dedicated /products/index endpoint.
    if (tenantId) {
      (async () => {
        for (const s of all) {
          const prods = asArray(s.products).map((p) => ({ product_code: p.product_code, product_name: p.product_name, unit: p.sale_unit, stock: p.stock }));
          if (prods.length) await upsertProducts(tenantId, s.store_id, { store_code: s.store_code, store_name: s.store_name }, prods);
        }
        setLastSync(Date.now());
        try { window.dispatchEvent(new Event('nexora:synced')); } catch { /* best effort */ }
      })();
    }

    const withProduct = all.filter((s) => (s.products || [])[0]);
    const total = all.reduce((sum, s) => sum + (s.products || []).length, 0);
    setStatus({
      state: 'ok',
      message: withProduct.length
        ? `${total} match(es) across ${withProduct.length} store(s).`
        : (total ? `${total} match(es).` : 'No products matched in any store.'),
    });
  }

  // ── Cross-store selection (reused from the main Stock Availability screen) ──
  // One product is the GREEN "source" (the row clicked); the same product is
  // auto-resolved (BLUE) in every other store — first by an instant exact
  // product_code match against the loaded results, then by the server-side
  // fuzzy matcher (api.syncStockSelection) for any store the exact code missed.
  // Each resolved store's core is loaded so its Chart/Batch/Purchase/Sales show
  // that product. Never fabricated, never cross-store mixed.
  async function loadStoreCore(storeId, product) {
    const cacheKey = `${storeId}:${product.product_code}`;
    const cached = detailCacheRef.current.get(cacheKey);
    if (isStockCoreFresh(cached)) return cached;
    const result = await coreLimitRef.current(() => api.getStockCore(storeId, product.product_code, session, { months: 4 }));
    const core = {
      product,
      batches: asArray(result?.batches),
      purchases: asArray(result?.purchases),
      sales: asArray(result?.sales),
      movement: asArray(result?.movement),
      fetchedAt: Date.now()
    };
    if (core.batches.length || core.purchases.length || core.sales.length || core.movement.length) {
      detailCacheRef.current.set(cacheKey, core);
    }
    return core;
  }

  function handleProductSelect(sourceStore, product) {
    const storeId = sourceStore.store_id;
    const searchId = searchIdRef.current;
    setSelectionState(selectionStateForClick(storeId, product.product_code));

    const exactResults = [];
    const exactStoreIds = new Set();
    stores.forEach((s) => {
      if (s.store_id === storeId) return;
      const m = (s.products || []).find((p) => p.product_code === product.product_code);
      if (m) {
        exactResults.push({ store_id: s.store_id, product: { product_code: m.product_code, product_name: m.product_name, mrp: m.mrp }, match_type: 'EXACT_PRODUCT_CODE', score: 100 });
        exactStoreIds.add(s.store_id);
      }
    });
    // Load EVERY matched store's core, including NMW — a store user doesn't see
    // the NMW tables but the NMW summary tiles below (stock/expiry/PTR/MRP) need
    // its batch data. The matrix handles the NMW display gating, not this.
    if (exactResults.length) {
      setSelectionState((cur) => applySyncResult(cur, storeId, product.product_code, buildSynchronizedMap(exactResults)));
      exactResults.forEach((match) => {
        loadStoreCore(match.store_id, match.product)
          .then((core) => { if (searchIdRef.current === searchId) setStoreDetails((prev) => ({ ...prev, [match.store_id]: core })); })
          .catch(() => setStoreDetails((prev) => ({ ...prev, [match.store_id]: { product: match.product, batches: [], purchases: [], sales: [], movement: [] } })));
      });
    }
    loadStoreCore(storeId, product)
      .then((core) => { if (searchIdRef.current === searchId) setStoreDetails((prev) => ({ ...prev, [storeId]: core })); })
      .catch(() => setStoreDetails((prev) => ({ ...prev, [storeId]: { product, batches: [], purchases: [], sales: [], movement: [] } })));
    syncCrossStoreSelection(storeId, product, searchId, exactStoreIds, exactResults);
  }

  async function syncCrossStoreSelection(sourceStoreId, product, searchId, exactStoreIds, exactResults) {
    if (!product?.product_code) return;
    const targetStoreIds = stores.map((s) => s.store_id).filter((id) => id && id !== sourceStoreId && !exactStoreIds.has(id));
    if (!targetStoreIds.length) return;
    const ticket = ++syncTicketRef.current;
    let response;
    try {
      response = await api.syncStockSelection(sourceStoreId, product.product_code, product.product_name, targetStoreIds, session, { tenantId });
    } catch { return; }
    if (ticket !== syncTicketRef.current || searchIdRef.current !== searchId) return;
    const matches = asArray(response?.results).filter((r) => r.product && r.match_type !== 'NO_MATCH');
    const freshSynchronized = buildSynchronizedMap([...exactResults, ...asArray(response?.results)]);
    setSelectionState((cur) => applySyncResult(cur, sourceStoreId, product.product_code, freshSynchronized));
    await Promise.all(matches.map(async (match) => {
      const known = (searchProductsByStore.get(match.store_id) || []).find((row) => row.product_code === match.product.product_code);
      const targetProduct = known || { product_code: match.product.product_code, product_name: match.product.product_name, mrp: match.product.mrp };
      try {
        const core = await loadStoreCore(match.store_id, targetProduct);
        if (ticket === syncTicketRef.current && searchIdRef.current === searchId) setStoreDetails((prev) => ({ ...prev, [match.store_id]: core }));
      } catch { /* keep previously loaded detail on a transient failure */ }
    }));
  }

  const selectionFor = (storeId) => selectionForStore(selectionState, storeId);

  useEffect(() => {
    if (searchMode === 'batch') {
      const batch = batchNo.trim();
      const mrp = batchMrp.trim();
      const product = batchProduct.trim().replace(/\s+/g, ' ');
      if (!batch && !mrp && !product) {
        searchIdRef.current += 1;
        setStores([]); setStoreDetails({}); setSelectionState(emptySelectionState());
        setStatus({ state: 'idle', message: 'Enter a batch number, MRP, or product name.' });
        return undefined;
      }
      const timer = setTimeout(() => runSearch('', { batch, mrp, product }), 200);
      return () => clearTimeout(timer);
    }
    const value = query.trim().replace(/\s+/g, ' ');
    if (value.length < 2) {
      searchIdRef.current += 1;
      setStores([]); setStoreDetails({}); setSelectionState(emptySelectionState());
      setStatus({ state: 'idle', message: 'Type at least 2 characters to search.' });
      return undefined;
    }
    const timer = setTimeout(() => runSearch(value), 200);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, onlyStock, tenantId, searchMode, batchNo, batchMrp, batchProduct]);

  // Stores that matched, in backend order but with the device's OWN (native)
  // store pushed to the very end (owner ruling 2026-10-03).
  const orderedStores = useMemo(() => {
    const withProduct = stores.filter((s) => (s.products || [])[0]);
    const rest = withProduct.filter((s) => s.store_id !== nativeStoreId);
    const native = withProduct.filter((s) => s.store_id === nativeStoreId);
    return [...rest, ...native];
  }, [stores, nativeStoreId]);

  // Before any search, the screen showed nothing but a one-line placeholder
  // message -- the operator had to search once just to see what the layout
  // even looks like. tenantStores (the store list) loads independently of
  // search, so render the SAME matrix immediately with empty product lists:
  // every column (Store Grid/Chart/Batch/Purchase/Sales) renders its own
  // normal empty state, giving a real skeleton of the actual screen instead
  // of a blank page.
  const skeletonStores = useMemo(() => {
    const rest = tenantStores.filter((s) => s.store_id !== nativeStoreId);
    const native = tenantStores.filter((s) => s.store_id === nativeStoreId);
    return [...rest, ...native].map((s) => ({ ...s, products: [] }));
  }, [tenantStores, nativeStoreId]);

  // On a NEW online result set, auto-select the first store's top product as the
  // shared comparison context (offline selection is handled in runSearch). A
  // user's later click supersedes it; this only fires when the result set
  // changes, never on a selection change, so it can't fight the user.
  const resultKey = stores.map((s) => `${s.store_id}:${(s.products || [])[0]?.product_code ?? ''}`).join('|');
  useEffect(() => {
    if (offline) return;
    const first = orderedStores.find((s) => (s.products || [])[0]);
    if (first) handleProductSelect(first, first.products[0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resultKey]);

  return (
    <section className="screen-panel sv-screen">
      {!title && !embedded ? <ScreenHeader title={compact ? 'Quick Stock' : 'Stock Enquiry'} /> : null}
      <div className="sv-toolbar">
        {title ? <h1 className="sv-toolbar__title">{title}</h1> : null}
        <div className="ns-search__tabs" role="tablist" aria-label="Search mode">
          <button type="button" role="tab" aria-selected={searchMode === 'product'} className={`ns-search__tab${searchMode === 'product' ? ' ns-search__tab--active' : ''}`} onClick={() => setSearchMode('product')}>Product</button>
          <button type="button" role="tab" aria-selected={searchMode === 'batch'} className={`ns-search__tab${searchMode === 'batch' ? ' ns-search__tab--active' : ''}`} onClick={() => setSearchMode('batch')}>Batch / MRP</button>
        </div>
        <div className="sv-toolbar__fields">
          {searchMode === 'product' ? (
            <input
              className="sv-search"
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search name or code — use * as wildcard (e.g. *karma)"
              aria-label="Search products"
              autoFocus
            />
          ) : (
            <>
              <input className="sv-search" aria-label="Batch number" value={batchNo} onChange={(event) => setBatchNo(event.target.value)} placeholder="Batch number" autoFocus />
              <input className="sv-search" aria-label="MRP" value={batchMrp} onChange={(event) => setBatchMrp(event.target.value)} placeholder="MRP" />
              <input className="sv-search" aria-label="Product name" value={batchProduct} onChange={(event) => setBatchProduct(event.target.value)} placeholder="Product name" />
            </>
          )}
        </div>
        {searchMode === 'product' && (
          <label className="sv-check" title="Only stores where the product has stock">
            <input type="checkbox" checked={onlyStock} onChange={(event) => setOnlyStock(event.target.checked)} />
            <span>In-stock only</span>
          </label>
        )}
        {offline && (
          <span
            className="sv-offline"
            title={lastSync ? `Cached data as of ${formatSyncTime(lastSync)}` : 'No cached data yet'}
          >
            ● Offline — cached
          </span>
        )}
        <span className={`sv-status sv-status--${status.state}`}>{status.message}</span>
      </div>
      <StoreComparisonMatrix
        stores={orderedStores.length ? orderedStores : skeletonStores}
        storeDetails={orderedStores.length ? storeDetails : {}}
        selectionFor={selectionFor}
        onProductSelect={handleProductSelect}
        superAdmin={superAdmin}
        session={session}
        rows={compact ? SCM_ROWS_COMPACT : SCM_ROWS}
        notice={status.message}
        loadingStores={orderedStores.length === 0 && skeletonStores.length === 0}
      />
    </section>
  );
}

function ScreenHeader({ title, subtitle }) {
  return (
    <header className="screen-header">
      <div>
        <h2>{title}</h2>
        {subtitle ? <p>{subtitle}</p> : null}
      </div>
    </header>
  );
}
