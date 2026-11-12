// App-wide display formatters, extracted from App.jsx (NEXORA MEDIQ Phase 4
// structural refactor, see docs/NEXORA_MEDIQ_AUDIT/20_PHASE4_EXTRACTION_PROGRESS_AND_CORRECTED_MAP.md
// and 22_PHASE4_ORDER_WORKSPACE_EXTRACTION_REPORT.md). Pure, no React --
// used by Order Workspace, the Label Exporter screen and the Procurement
// rendering region. No behavior changed in the move.

export function fmtOwQty(value) {
  if (value === null || value === undefined || value === '') return '—';
  const n = Number(value);
  return Number.isFinite(n) ? n.toLocaleString(undefined, { maximumFractionDigits: 2 }) : '—';
}

export function fmtOwMoney(value) {
  if (value === null || value === undefined || value === '') return '—';
  const n = Number(value);
  return Number.isFinite(n) ? n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—';
}

export function fmtOwDate(value) {
  if (!value) return '—';
  const raw = String(value).slice(0, 10);
  const parts = raw.split('-');
  return parts.length === 3 ? `${parts[2]}/${parts[1]}/${parts[0].slice(2)}` : raw;
}

export function fmtOwPct(value) {
  if (value === null || value === undefined || value === '' || Number.isNaN(Number(value))) return '—';
  return `${Number(value).toFixed(2)}%`;
}

// Explicit sign for Adjustment (never collapse -3 to 3, always show +5 not 5).
export function fmtOwSigned(value) {
  const n = Number(value) || 0;
  const body = Math.abs(n).toLocaleString(undefined, { maximumFractionDigits: 2 });
  return n > 0 ? `+${body}` : n < 0 ? `-${body}` : '0';
}

// Landing cost % = margin between PTR (selling-in price) and Cost (net landed
// cost, already inclusive of the synced offer/product-discount/scheme), i.e.
// how much PTR sits above Cost.
export function owLandingPct(ptr, cost) {
  const p = Number(ptr); const c = Number(cost);
  if (!Number.isFinite(p) || !Number.isFinite(c) || p <= 0) return null;
  return ((p - c) / p) * 100;
}
