// Canonical number/currency formatting for this app. One place, not the
// several ad hoc helpers found scattered through supplier-stock-client's
// App.jsx (at least 4 different formatting call sites for the same data).
// Values from the backend are not guaranteed numeric (raw SP pass-through
// endpoints may return strings or nulls) — every formatter here tolerates
// that defensively instead of assuming a clean number.

// Number(null) and Number('') both coerce to the finite value 0, so a
// missing/blank field would otherwise render as a real zero instead of
// "no value" — reject null/undefined/blank explicitly before coercing.
function toFiniteNumber(value) {
  if (value === null || value === undefined) return null;
  if (typeof value === 'string' && value.trim() === '') return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

export function formatQty(value) {
  const n = toFiniteNumber(value);
  if (n === null) return '—';
  return n.toLocaleString('en-IN', { maximumFractionDigits: 2 });
}

export function formatCurrency(value) {
  const n = toFiniteNumber(value);
  if (n === null) return '—';
  return `₹${n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatDate(value) {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
}

export function isLowStock(value, threshold = 10) {
  const n = toFiniteNumber(value);
  return n !== null && n > 0 && n <= threshold;
}

export function isOutOfStock(value) {
  const n = toFiniteNumber(value);
  return n === null || n <= 0;
}
