// Order Workspace display facts. Pure data only: these helpers never invent
// quantities, reasons, or workflow totals. Callers pass the row fields the
// legacy order API already returned.

// Previous Decisions docks under the grid by default (owner, 2026-10-25).
// Hiding it in layout settings brings back the per-row info button instead.
export const OW_PANEL_DEFS = [
  { key: 'trend', label: 'Monthly Trend' },
  { key: 'purchase', label: 'Purchase / GRN' },
  { key: 'sales', label: 'Bill / Sales' },
  { key: 'history', label: 'Previous Decisions' },
];

export const OW_PANELS_DEFAULT = [
  { key: 'trend', dock: 'side', hidden: false },
  { key: 'purchase', dock: 'side', hidden: false },
  { key: 'sales', dock: 'side', hidden: false },
  { key: 'history', dock: 'bottom', hidden: false },
];

export const OW_LAYOUT_DEFAULT = {
  rowSize: 'normal',
  rowWeight: 'normal',
  sidePosition: 'right',
  sideHidden: false,
  sideWidth: 'normal',
  bottomHeight: 'normal',
  qtyCheckStyle: 'tick',
  panels: OW_PANELS_DEFAULT,
};

// Saved settings -> a complete layout. Unknown panel keys are dropped.
// A panel an older save does not mention is appended with its default dock.
// Row font stays Normal when the saved value is missing or unrecognised,
// which is what older layouts (saved before the font control existed) need.
export function owNormalizeLayout(saved) {
  const merged = { ...OW_LAYOUT_DEFAULT, ...(saved || {}) };
  const known = new Set(OW_PANEL_DEFS.map((p) => p.key));
  const panels = (Array.isArray(merged.panels) ? merged.panels : [])
    .filter((p) => p && known.has(p.key))
    .map((p) => ({ key: p.key, dock: p.dock === 'bottom' ? 'bottom' : 'side', hidden: Boolean(p.hidden) }));
  OW_PANELS_DEFAULT.forEach((d) => { if (!panels.some((p) => p.key === d.key)) panels.push({ ...d }); });
  if (merged.sidePosition !== 'left') merged.sidePosition = 'right';
  if (!['compact', 'normal', 'large'].includes(merged.rowSize)) merged.rowSize = 'normal';
  if (merged.rowWeight !== 'bold') merged.rowWeight = 'normal';
  if (!['narrow', 'normal', 'wide'].includes(merged.sideWidth)) merged.sideWidth = 'normal';
  if (!['small', 'normal', 'large'].includes(merged.bottomHeight)) merged.bottomHeight = 'normal';
  merged.sideHidden = Boolean(merged.sideHidden);
  if (merged.qtyCheckStyle !== 'text') merged.qtyCheckStyle = 'tick';
  return { ...merged, panels };
}

export function owNumber(value) {
  if (value === null || value === undefined || value === '') return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

export function owSum(values) {
  let sum = 0;
  let any = false;
  for (const value of values) {
    const n = owNumber(value);
    if (n == null) continue;
    sum += n;
    any = true;
  }
  return any ? sum : null;
}

function cleanName(name) {
  return String(name ?? '').replace(/\s+/g, ' ').trim();
}

// One selected order line, read from the active loader's row. `edit` is the
// in-progress quantity; 0 is a real "do not order" value and is preserved.
export function owLineFromRow(view, row, options = {}) {
  if (!row) return null;
  const lower = view === 'qty' || view === 'pending';
  const code = lower ? row.productcode : row.ProductCode;
  const originalQty = owNumber(lower ? row.orgorderqty : row.OrgOrderQty);
  const loadedFinal = owNumber(lower ? row.orderqty : row.OrderQty);
  const edited = options.edit;
  const finalQty = edited != null && edited !== '' ? owNumber(edited) : loadedFinal;
  let qtyCheck = null;
  if (view === 'qty') qtyCheck = options.reviewed ? 'checked' : 'pending';
  else if (view === 'pending') qtyCheck = 'checked';
  else if (view === 'supplier' || view === 'assigned' || view === 'review') {
    const raw = row.Qtycheck;
    if (raw === null || raw === undefined) qtyCheck = options.qtyChecked ? 'checked' : 'unknown';
    else qtyCheck = (Number(raw) === 1 || options.qtyChecked) ? 'checked' : 'pending';
  }
  let assignment = null;
  if (view === 'supplier') assignment = Number(options.assignedStatus) === 1 ? 'assigned' : 'open';
  else if (view === 'assigned') assignment = 'assigned';
  else if (view === 'pending') assignment = 'open';
  const supplierOnRow = lower ? null : (row.OrSupplier || null);
  return {
    code: code ?? null,
    name: cleanName(lower ? row.productname : row.ProductName) || (code != null ? `#${code}` : ''),
    unit: (lower ? row.unitdescription : row.UnitDescription) || null,
    pack: owNumber(lower ? row.saleunit : row.SaleUnit),
    stock: owNumber(lower ? row.totalstock : row.TotalStock),
    mrp: owNumber(lower ? row.mrp : row.MRP),
    salesQty: owNumber(lower ? row.slsqty : row.SLSQty),
    maxQty: owNumber(lower ? row.maxsaleqty : row.MaxQty),
    originalQty,
    finalQty,
    offer: Boolean(row.IsOffer),
    wanted: (lower ? row.wantedtype : row.WantedType) || null,
    qtyCheck,
    assignment,
    supplierName: options.supplierName || supplierOnRow || null,
    supplierStock: options.stockMode ? owNumber(row.S_Stock) : null,
    remarks: lower ? null : (row.Remarks || null),
    lastSaleDate: lower ? (row.lastsaledate || null) : null,
    lastReceivedDate: lower ? (row.lastreceiveddate || null) : null,
  };
}

// Describes the line from fields that are actually present. This is context
// for the buyer, not an approval and not a new recommendation.
export function owLineNote(line, view, { finalized = false } = {}) {
  if (!line) return '';
  if (finalized) return 'This order is finalized. Quantities stay read-only until it is reopened.';
  if (line.finalQty === 0) return 'Final quantity is 0, so this product is not ordered.';
  if (line.originalQty != null && line.finalQty != null && Number(line.originalQty) !== Number(line.finalQty)) {
    return 'Final quantity differs from the original quantity loaded for this line.';
  }
  if (view === 'qty' && line.qtyCheck === 'pending') {
    return 'Qty Check is pending. Enter saves the quantity. Up or Down saves it and moves to the next row.';
  }
  if (view === 'qty' && line.qtyCheck === 'checked') return 'Reviewed in this session. The row stays until the next reload.';
  if (view === 'pending') return 'Reviewed, and not yet assigned to a supplier.';
  if (view === 'supplier' && line.assignment === 'assigned') {
    return line.supplierName ? `Assigned to ${line.supplierName}.` : 'Assigned to the selected supplier.';
  }
  if (view === 'supplier' && line.assignment === 'open') {
    return line.supplierName ? `Open. Enter assigns ${line.supplierName}.` : 'Pick a supplier before this line can be assigned.';
  }
  if (view === 'assigned') {
    return line.supplierName ? `On ${line.supplierName}'s order.` : 'On the selected supplier order.';
  }
  if (view === 'review') return 'Open order line. Edit the quantity in the grid.';
  return '';
}

// Totals for the rows currently on screen. Original qty is omitted (null)
// when the loader did not send orgorderqty / OrgOrderQty — never shown as 0.
// Workflow counts are passed through from the server payload when present.
export function owWorkspaceSummary({
  loading = false,
  rows = [],
  qtyOf,
  originalOf,
  offerOf,
  qtyCheckedOf,
  workflow = null,
} = {}) {
  if (loading) {
    return {
      loading: true,
      products: null,
      originalQty: null,
      finalQty: null,
      qtyCheckChecked: null,
      qtyCheckKnown: null,
      offers: null,
      zeroQty: null,
      assignedLines: null,
      pendingLines: null,
      openLines: null,
      status: null,
    };
  }
  const list = Array.isArray(rows) ? rows : [];
  let checked = 0;
  let known = 0;
  let offers = 0;
  let zeros = 0;
  const finals = [];
  const originals = [];
  for (const row of list) {
    const qty = qtyOf ? qtyOf(row) : null;
    finals.push(qty);
    originals.push(originalOf ? originalOf(row) : null);
    if (owNumber(qty) === 0) zeros += 1;
    if (offerOf && offerOf(row)) offers += 1;
    const status = qtyCheckedOf ? qtyCheckedOf(row) : null;
    if (status === 'checked' || status === 'pending' || status === 'unknown') {
      known += 1;
      if (status === 'checked') checked += 1;
    }
  }
  const workflowNumber = (key) => (workflow && workflow[key] != null && workflow[key] !== '' ? owNumber(workflow[key]) : null);
  return {
    loading: false,
    products: list.length,
    originalQty: owSum(originals),
    finalQty: owSum(finals),
    qtyCheckChecked: known ? checked : null,
    qtyCheckKnown: known || null,
    offers,
    zeroQty: zeros,
    assignedLines: workflowNumber('assigned_lines'),
    pendingLines: workflowNumber('qty_pending'),
    openLines: workflowNumber('unassigned_lines'),
    status: workflow && workflow.status ? String(workflow.status) : null,
  };
}
