// Cascade key builder + exact-match normalization for the Similar Search flow
// on the Supplier Stock Analysis screen. Pure, no React/API dependencies.

// Deliberately diverges from the backend's product_mapping DEFAULT_DOSAGE_TERMS
// (which keeps "SR" on purpose, for the deterministic matching engine - see
// backend/modules/product_mapping/normalization.py). Here we want the broadest
// usable brand key for a last-resort search, so qualifier words like SR/ER/PLUS
// are stripped too. Do not "unify" this list with the backend's without
// checking why they differ - they serve different purposes.
const NUMBER_RE = /^\d+(\.\d+)?%?$/;
const GLUED_NUMBER_UNIT_RE = /^\d+(\.\d+)?(ML|MG|MCG|GM|GRAM|IU|L|KG)$/;
const STRIP_WORDS = new Set([
  'TAB', 'TABS', 'TABLET', 'TABLETS',
  'CAP', 'CAPS', 'CAPSULE', 'CAPSULES',
  'SYP', 'SYRUP', 'SUSP', 'SUS', 'SUSPENSION',
  'INJ', 'INJECTION', 'DROP', 'DROPS',
  'CREAM', 'OINT', 'OINTMENT', 'GEL', 'LOTION',
  'SPRAY', 'SOAP', 'POWDER', 'SACHET', 'SOLN', 'SOLUTION',
  'STRIP', 'STRIPS', 'SR', 'ER', 'XR', 'DS', 'FORTE', 'PLUS',
  'MOUTH', 'WASH', 'ML', 'MG', 'MCG', 'GM', 'IU'
]);
const LOOSE_EXACT_STRIP_WORDS = new Set([
  'TAB', 'TABS', 'TABLET', 'TABLETS',
  'CAP', 'CAPS', 'CAPSULE', 'CAPSULES',
  'SYP', 'SYRUP', 'SUSP', 'SUS', 'SUSPENSION',
  'INJ', 'INJECTION', 'DROP', 'DROPS',
  'CREAM', 'OINT', 'OINTMENT', 'GEL', 'LOTION',
  'SPRAY', 'SOAP', 'POWDER', 'SACHET', 'SOLN', 'SOLUTION',
  'STRIP', 'STRIPS',
  'ML', 'MG', 'MCG', 'GM', 'GRAM', 'IU', 'KG', 'L'
]);

function tokenize(name) {
  return String(name || '')
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, ' ')
    .trim()
    .split(' ')
    .filter(Boolean);
}

function isStrippable(token) {
  return NUMBER_RE.test(token) || GLUED_NUMBER_UNIT_RE.test(token) || STRIP_WORDS.has(token);
}

// Walks tokens from the end, dropping strength/unit/dosage-form/qualifier
// tokens until it hits the first "real" brand token.
// "LASIX 4ML INJ" -> "LASIX"; "AB PHYLLINE SR 200 TAB" -> "AB PHYLLINE".
export function buildBrandKey(name) {
  const tokens = tokenize(name);
  if (!tokens.length) return '';
  let end = tokens.length;
  while (end > 1 && isStrippable(tokens[end - 1])) end -= 1;
  return tokens.slice(0, end).join(' ');
}

export function buildPrefixSearchKey(name, minChars = 6) {
  const brandKey = buildBrandKey(name);
  const fallback = String(name || '').trim().replace(/\s+/g, ' ').toUpperCase();
  const source = brandKey || fallback;
  if (!source) return '';
  const size = Math.max(1, Number(minChars) || 6);
  return source.length <= size ? source : source.slice(0, size).trim();
}

// Ordered, deduplicated cascade of search keys to try against the existing
// all-store product search endpoint (broadest/last-resort key last).
export function buildSearchCascade(name) {
  const trimmed = String(name || '').trim().replace(/\s+/g, ' ');
  if (!trimmed) return [];
  const tokens = trimmed.split(' ');
  const steps = [
    trimmed,
    tokens.slice(0, 2).join(' '),
    tokens.slice(0, 1).join(' '),
    buildBrandKey(trimmed)
  ];
  const seen = new Set();
  return steps.filter((step) => {
    const key = step.toUpperCase();
    if (!step || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

// Mirrors the backend's normalize_product_name (product_mapping/normalization.py):
// uppercase, strip every separator/punctuation, keep digits. Used only to decide
// the display-only EXACT MATCH badge - the actual ranking authority is always
// the backend's /api/product-mapping/candidates total_score.
export function normalizeForBadge(name) {
  return String(name || '').toUpperCase().replace(/[^A-Z0-9]+/g, '');
}

// Compact comparison key for "same medicine, different spacing/unit spelling"
// checks in the UI. Examples:
// "DYTOR PLUS 5 TAB" -> "DYTORPLUS5"
// "DYTORPLUS5MG TAB" -> "DYTORPLUS5"
export function normalizeForLooseExact(name) {
  const tokens = String(name || '')
    .toUpperCase()
    .match(/[A-Z]+|\d+(?:\.\d+)?/g);
  if (!tokens?.length) return '';
  return tokens
    .filter((token) => !LOOSE_EXACT_STRIP_WORDS.has(token))
    .join('');
}
