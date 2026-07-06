// Frontend-only supplier abbreviation. Used to label supplier chips/cards when
// the backend has not (yet) stored an explicit abbreviation. Persistence +
// editing lands in the backend "Supplier Contact Maintenance" iteration; until
// then this derives a stable short label from the supplier name.
//
// Rule (owner-directed): show the FIRST MEANINGFUL WORD, dropping honorifics and
// generic trade suffixes. Examples:
//   "SRI BALAJI PHARMA"            → "BALAJI"
//   "SRI MEENACHI MEDICAL AGENCY"  → "MEENACHI"
//   "SRI RAM MEDICALS"             → "RAM"
// The full name is always kept in the card/chip tooltip (title=).

// Words to ignore when choosing the meaningful word (compared lowercase, with
// punctuation stripped). Covers honorific prefixes AND generic trade suffixes.
const NOISE = new Set([
  // honorifics / fillers
  'sri', 'sree', 'shri', 'the', 'new', 'ms', 'messrs', 'messr',
  // generic trade words
  'medical', 'medicals', 'agency', 'agencies', 'pharma', 'pharmacy',
  'pharmaceuticals', 'pharmaceutical', 'distributors', 'distributor',
  'distribution', 'traders', 'trading', 'enterprises', 'enterprise',
  'pvt', 'ltd', 'limited', 'private', 'company', 'co', 'and', 'agencys',
])

const clean = (w: string) => w.toLowerCase().replace(/[^a-z0-9]/g, '')

/**
 * Derive a short supplier label — the first meaningful word of the name,
 * ignoring honorifics and generic trade suffixes. Falls back to the first
 * word, then the supplier code, then "?".
 */
export function supplierAbbrev(name?: string | null, code?: string | null): string {
  const src = (name ?? '').trim()
  if (!src) return (code ?? '?').replace(/[^a-z0-9]/gi, '').slice(0, 6).toUpperCase() || '?'
  const words = src.split(/[\s./,-]+/).filter(Boolean)
  const meaningful = words.find((w) => !NOISE.has(clean(w)))
  return (meaningful ?? words[0] ?? src).toUpperCase()
}
