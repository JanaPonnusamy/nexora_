// Pure helpers for the Rate Analysis screen (kept JSX-free so node --test can load them).

export const toNum = (v) => (v === '' || v === undefined || v === null ? null : Number(String(v).replace(/,/g, '')));
const isNum = (v) => /^\d+(\.\d+)?$/.test(String(v || '').replace(/,/g, '').trim());

// One quoted line -> {text, mrp, ptr}. Excel paste is tab separated (blank PTR
// cells survive, a leading S.No cell is dropped); typed lines end with
// "MRP PTR" or just "PTR".
export function parseQuoteLine(raw) {
  const line = String(raw || '').replace(/\s+$/, '');
  if (!line.trim()) return null;
  if (line.includes('\t')) {
    let cells = line.split('\t').map((c) => c.trim());
    if (cells.length > 1 && /^\d+[.,)]?$/.test(cells[0])) cells = cells.slice(1);
    const textCells = [];
    let i = 0;
    while (i < cells.length && !isNum(cells[i])) { if (cells[i]) textCells.push(cells[i]); i += 1; }
    const nums = cells.slice(i);
    if (!textCells.length) return null;
    return { text: textCells.join(' '), mrp: toNum(nums[0]), ptr: toNum(nums[1]) };
  }
  const body = line.replace(/^\s*\d+\s*[.,)-]\s*(?=\D)/, '').trim();
  let m = /^(.*?)[\s,|]+(\d[\d,]*(?:\.\d+)?)[\s,|]+(\d[\d,]*(?:\.\d+)?)$/.exec(body);
  if (m) return { text: m[1].trim(), mrp: toNum(m[2]), ptr: toNum(m[3]) };
  m = /^(.*?)[\s,|]+(\d[\d,]*(?:\.\d+)?)$/.exec(body);
  if (m) return { text: m[1].trim(), mrp: null, ptr: toNum(m[2]) };
  return { text: body, mrp: null, ptr: null };
}

export function fmtCell(v, format) {
  if (v === null || v === undefined || v === '') return '';
  if (format === 'date') {
    const s = String(v).slice(0, 10);
    const [y, mo, d] = s.split('-');
    return d ? `${d}-${mo}-${y}` : s;
  }
  if (typeof v !== 'number') return String(v);
  if (format === 'money') return v.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (format === 'int') return Math.round(v).toLocaleString('en-IN');
  if (format === 'num1' || format === 'pct') return v.toLocaleString('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  return String(v);
}
