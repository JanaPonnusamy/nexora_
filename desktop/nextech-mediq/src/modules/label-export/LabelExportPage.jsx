// Label Exporter — ported from desktop/supplier-stock-client/src/App.jsx's
// LabelExporter component (owner: "already we have label exporter just wire
// here, no need to rebuild"). Behavior/business rules are unchanged; only the
// API layer, surrounding chrome and CSS are adapted to this app's
// apiGet/apiPost/apiPut client, PageLayout shell and --ntm-* styling —
// same approach as modules/legacy-order/LegacyOrderPage.jsx.
//
// Dropped vs. the original (same simplifications already made elsewhere in
// this app, e.g. non-moving-stock): row virtualization (@tanstack/react-virtual
// isn't a dependency here — plain row mapping is fine at this app's scale),
// drag-to-reorder column headers (column settings still support show/hide +
// width), WhatsApp auto-share, and the Electron IPC session-file bridge
// (replaced with a single localStorage layout/filter key, matching
// NonMovingStockPage's _LAYOUT_KEY convention).
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { PageLayout } from '../../layouts/PageLayout.jsx';
import { useAuth } from '../../contexts/AuthContext.jsx';
import { isSuperAdmin } from '../../navigation/access.js';
import * as api from '../../services/labelExportService.js';
import { downloadBlob } from '../../services/labelExportService.js';
import './labelExport.css';

// ---------- Pure helpers (ported verbatim from the old App.jsx) ----------

const LABEL_STOCK_FILTERS = [
  { value: 'every', label: 'All (no stock/sale filter)' },
  { value: 'all', label: 'Stock > 0, or sold <90d, or new' },
  { value: 'in_stock', label: 'In stock only' },
  { value: 'zero_recent_sale', label: 'Zero, sold <90d' },
  { value: 'zero_stale', label: 'Zero, no sale >90d' },
];

const LABEL_REMARKS_PRESETS = [
  'Counter', 'Consumer', 'SYP', 'Cold Storage', 'Fragile', 'High Value', 'Fast Moving', 'Slow Moving', 'Check Unit Description',
];

const LABEL_UNIT_PRESETS = ['TAB', 'CAP', 'SYP', 'INJ', 'CREAM', 'LOT', 'PACK', 'SUG', 'DROPS', 'POWDER'];
const LABEL_LETTER_OPTIONS = Array.from({ length: 26 }, (_, i) => String.fromCharCode(65 + i));

const LABEL_COLUMNS = [
  { key: 'sno', label: '#', width: 32, locked: true },
  { key: 'code', label: 'Code', width: 85, locked: true },
  { key: 'product', label: 'Product', width: 220, locked: true },
  { key: 'oldUnit', label: 'Old Unit', width: 75 },
  { key: 'newUnit', label: 'New Unit', width: 85 },
  { key: 'saleUnit', label: 'Sale Unit', width: 65 },
  { key: 'oldLoc', label: 'Old Loc', width: 75 },
  { key: 'newLoc', label: 'New Loc', width: 120 },
  { key: 'stock', label: 'Stock', width: 55 },
  { key: 'lpd', label: 'LPD', width: 70 },
  { key: 'lsd', label: 'LSD', width: 70 },
  { key: 'review', label: 'Review', width: 55 },
];

function asArray(value) {
  if (Array.isArray(value)) return value;
  if (Array.isArray(value?.rows)) return value.rows;
  return [];
}

function fmtQty(value) {
  if (value === null || value === undefined || value === '') return '—';
  const n = Number(value);
  return Number.isFinite(n) ? n.toLocaleString(undefined, { maximumFractionDigits: 2 }) : '—';
}
function fmtMoney(value) {
  if (value === null || value === undefined || value === '') return '—';
  const n = Number(value);
  return Number.isFinite(n) ? n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—';
}
function fmtDate(value) {
  if (!value) return '—';
  const raw = String(value).slice(0, 10);
  const parts = raw.split('-');
  return parts.length === 3 ? `${parts[2]}/${parts[1]}/${parts[0].slice(2)}` : raw;
}
function fmtPct(value) {
  if (value === null || value === undefined || value === '' || Number.isNaN(Number(value))) return '—';
  return `${Number(value).toFixed(2)}%`;
}
function fmtDays(days, iso) {
  if (!iso) return '—';
  const n = Number(days);
  return Number.isFinite(n) ? `${n}d` : '—';
}
function fmtDateTime(iso) {
  if (!iso) return '';
  const d = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : `${iso}Z`);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toLocaleString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function lblOldUnit(row) { return String(row.old_unit_description || row.unit_description || '').trim(); }
function lblNewUnit(row) { return String(row.corrected_unit || row.unit_description || '').trim(); }
function lblUnitChanged(row) {
  return String(row.corrected_unit || '').trim() !== '' && lblNewUnit(row).toUpperCase() !== lblOldUnit(row).toUpperCase();
}
function lblOldLoc(row) { return String(row.old_sublocation || row.current_sublocation || '').trim(); }
function lblNewLoc(row) { return String(row.assigned_sublocation || '').trim(); }
function lblIsAssigned(row) { return lblNewLoc(row) !== ''; }
function lblReview(row) {
  return row.include_label === 'Y' ? 'INCLUDED' : row.include_label === 'N' ? 'EXCLUDED' : 'NOT_REVIEWED';
}
function lblAssignment(row) {
  const r = lblReview(row);
  if (r === 'NOT_REVIEWED') return 'NOT_STARTED';
  if (r === 'EXCLUDED') return 'NOT_REQUIRED';
  return lblIsAssigned(row) ? 'ASSIGNED' : 'PENDING';
}
// Zero stock AND no purchase/sale in the last 90 days (or never).
function lblIsStaleNoStock(row) {
  if (Number(row.total_stock) !== 0) return false;
  const purchaseStale = !row.last_purchase_date || Number(row.purchase_days) > 90;
  const saleStale = !row.last_sale_date || Number(row.sale_days) > 90;
  return purchaseStale && saleStale;
}
// Sale unit 1 but unit isn't TAB — likely a mis-set unit worth a second look.
function lblIsSaleUnitOneNotTab(row) {
  if (Number(row.sale_unit) !== 1) return false;
  const unit = lblNewUnit(row).trim().toUpperCase();
  return !!unit && unit !== 'TAB';
}
// Sale unit > 1 and live stock — marking N removes sellable stock from the list.
function lblHasSellableStockMultiUnit(row) {
  return Number(row.sale_unit) > 1 && Number(row.total_stock) > 0;
}
// Engine-assigned TAB box codes: <LETTER>0NN (A001, B025…). Named locations
// ("Counter", "SYP A") never match — used by "Clear New Loc" to spare them.
const LBL_AUTO_BOX_RE = /^[A-Za-z]0/;
function lblIsAutoBoxLoc(row) { return LBL_AUTO_BOX_RE.test(lblNewLoc(row)); }
// Shelf letter a box code belongs to — mirrors backend pdf_export.location_letter.
const LBL_LOC_SPLIT_RE = /^([A-Za-z]+)0*(\d+)$/;
function queueLocationLetter(location) {
  const match = LBL_LOC_SPLIT_RE.exec(String(location || '').trim());
  if (!match) return '';
  let letters = match[1].toUpperCase();
  if (letters.startsWith('SYP')) letters = letters.slice(3);
  return letters ? letters[0] : '';
}

// Mirrors backend dependencies.store_scope.assert_label_exporter_store_access.
function canChangeLabelStore(user) {
  if (isSuperAdmin(user)) return true;
  const role = user?.roles?.[0];
  return String(role?.store_code || '').trim().toUpperCase() === 'NMW';
}

const _LAYOUT_KEY = 'ntm.labelExport.layout.v1';
function loadLayout() {
  try {
    const raw = window.localStorage.getItem(_LAYOUT_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}
function saveLayout(layout) {
  try { window.localStorage.setItem(_LAYOUT_KEY, JSON.stringify(layout)); } catch { /* ignore */ }
}

function errorTitle(status) {
  if (status === 401) return 'Sign-in required';
  if (status === 403) return 'Not allowed';
  if (status === 0) return 'Network error';
  if (status >= 500) return 'Server error';
  return 'Request failed';
}

// ---------- Multi-select filter combo (Letter / Unit / Old Loc) ----------

function MultiPicker({ options, selected, onChange, placeholder = 'Any', noun = 'item' }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const wrapRef = useRef(null);

  useEffect(() => {
    function onDoc(e) { if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false); }
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  const term = query.trim().toLowerCase();
  const filtered = term ? options.filter((o) => o.toLowerCase().includes(term)) : options;

  function toggle(value) {
    const next = new Set(selected);
    if (next.has(value)) next.delete(value); else next.add(value);
    onChange(next);
  }
  const allShown = filtered.length > 0 && filtered.every((v) => selected.has(v));
  function toggleAll() {
    const next = new Set(selected);
    filtered.forEach((v) => (allShown ? next.delete(v) : next.add(v)));
    onChange(next);
  }

  const picked = Array.from(selected);
  const summary = picked.length === 0 ? placeholder
    : picked.length <= 3 && picked.every((v) => String(v).length <= 3) ? picked.join(', ')
      : picked.length === 1 ? picked[0] : `${picked.length} ${noun}s`;

  return (
    <div className="lblx-pick" ref={wrapRef}>
      <button type="button" className="lblx-pick-trigger" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        {summary}
      </button>
      {selected.size > 0 && !open && (
        <button type="button" className="lblx-pick-clear" title={`Clear ${noun} filter`} onClick={() => onChange(new Set())}>×</button>
      )}
      {open && (
        <div className="lblx-pick-list" role="listbox">
          <input
            className="lblx-pick-search"
            type="text"
            placeholder={`Search ${noun}...`}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
          />
          <div className="lblx-pick-options">
            {filtered.length > 1 && (
              <label className="lblx-pick-all">
                <input type="checkbox" checked={allShown} onChange={toggleAll} />
                All{term ? ' shown' : ''}
              </label>
            )}
            {filtered.map((value) => (
              <label key={value}>
                <input type="checkbox" checked={selected.has(value)} onChange={() => toggle(value)} />
                {value}
              </label>
            ))}
            {!filtered.length && <div className="lblx-pick-empty">No {noun}s match.</div>}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------- Editable combo (New Unit / New Loc cells) ----------

function EditCombo({ current, options, onPick, onCancel, placeholder }) {
  const [query, setQuery] = useState('');
  const wrapRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => { inputRef.current?.focus(); inputRef.current?.select(); }, []);
  useEffect(() => {
    function onDoc(e) { if (wrapRef.current && !wrapRef.current.contains(e.target)) onCancel(); }
    document.addEventListener('mousedown', onDoc, true);
    return () => document.removeEventListener('mousedown', onDoc, true);
  }, [onCancel]);

  const term = query.trim().toUpperCase();
  const base = term ? options.filter((o) => o.toUpperCase().includes(term)) : options;
  const matches = term && !base.some((o) => o.toUpperCase() === term) ? [term, ...base].slice(0, 30) : base.slice(0, 30);

  function commit(value) {
    const v = String(value || '').trim().toUpperCase();
    if (v) onPick(v); else onCancel();
  }
  function onKeyDown(event) {
    event.stopPropagation();
    if (event.key === 'Escape') { event.preventDefault(); onCancel(); }
    else if (event.key === 'Enter') { event.preventDefault(); commit(matches[0] ?? query); }
  }

  return (
    <div className="lblx-combo" ref={wrapRef} onClick={(e) => e.stopPropagation()}>
      <input
        ref={inputRef}
        className="lblx-combo-input"
        value={query}
        placeholder={current || placeholder}
        onChange={(e) => setQuery(e.target.value.toUpperCase())}
        onKeyDown={onKeyDown}
      />
      {matches.length > 0 && (
        <div className="lblx-combo-menu" role="listbox">
          {matches.map((value) => (
            <button type="button" key={value} className="lblx-combo-row" role="option" onClick={() => commit(value)}>
              <span>{value}</span>
              {value === String(current || '').toUpperCase() && <em>current</em>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------- Main page ----------

export function LabelExportPage() {
  const { tenantId, storeId, storeName, stores, user } = useAuth();
  const admin = isSuperAdmin(user);
  const canChangeStore = canChangeLabelStore(user);

  const savedLayout = useRef(loadLayout() || {});
  const [selectedLetters, setSelectedLetters] = useState(() => new Set(savedLayout.current.letters || []));
  const [q, setQ] = useState(savedLayout.current.search || '');
  const [selectedUnits, setSelectedUnits] = useState(() => new Set());
  const [unitSource, setUnitSource] = useState('new');
  const [selectedSublocs, setSelectedSublocs] = useState(() => new Set());
  const [boxNumber, setBoxNumber] = useState('');
  const [stockFilter, setStockFilter] = useState(savedLayout.current.stockFilter || 'all');
  const [reviewStatus, setReviewStatus] = useState('');
  const [onlyNullSublocation, setOnlyNullSublocation] = useState(false);
  const [onlySaleUnitGtOne, setOnlySaleUnitGtOne] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [editingUnitCode, setEditingUnitCode] = useState(null);
  const [editingLocationCode, setEditingLocationCode] = useState(null);

  const [hidden, setHidden] = useState(() => new Set(savedLayout.current.hidden || []));
  const [colSettingsOpen, setColSettingsOpen] = useState(false);
  const colSettingsRef = useRef(null);

  useEffect(() => {
    saveLayout({ letters: Array.from(selectedLetters), search: q, stockFilter, hidden: Array.from(hidden) });
  }, [selectedLetters, q, stockFilter, hidden]);

  useEffect(() => {
    if (!colSettingsOpen) return undefined;
    function onClickOutside(e) {
      if (colSettingsRef.current && !colSettingsRef.current.contains(e.target)) setColSettingsOpen(false);
    }
    document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, [colSettingsOpen]);

  const visibleCols = useMemo(() => LABEL_COLUMNS.filter((c) => !hidden.has(c.key)), [hidden]);

  const [rows, setRows] = useState([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const [selectedCodes, setSelectedCodes] = useState(() => new Set());
  const [status, setStatus] = useState({ state: 'idle', message: 'Pick a letter and search.' });
  const [savingCode, setSavingCode] = useState('');
  const [remarksDrafts, setRemarksDrafts] = useState({});
  const [unitOptions, setUnitOptions] = useState([]);
  const [unitChoices, setUnitChoices] = useState([]);
  const [sublocOptions, setSublocOptions] = useState([]);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [toast, setToast] = useState(null);
  const toastTimer = useRef(null);
  const [confirm, setConfirm] = useState(null);
  const searchRequestRef = useRef(0);

  function flashToast(text, kind = 'ok') {
    setToast({ text, kind });
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), kind === 'ok' ? 1400 : 2800);
  }

  const activeLetter = selectedLetters.size === 1 ? Array.from(selectedLetters)[0] : '';
  const [letterLock, setLetterLock] = useState(null);
  const [lockBusy, setLockBusy] = useState(false);
  const [exportBusy, setExportBusy] = useState(false);
  const isLocked = !!(letterLock && letterLock.locked && letterLock.letter === activeLetter);

  const refreshLetterLock = useCallback((letter) => {
    if (!letter || !tenantId || !storeId) { setLetterLock(null); return; }
    api.getLabelLetterLock(tenantId, storeId, letter).then(setLetterLock).catch(() => setLetterLock(null));
  }, [tenantId, storeId]);
  useEffect(() => { refreshLetterLock(activeLetter); }, [activeLetter, refreshLetterLock]);

  function toggleLetterLock() {
    if (!activeLetter || lockBusy) return;
    setLockBusy(true);
    const call = isLocked ? api.unlockLabelLetter(tenantId, storeId, activeLetter) : api.lockLabelLetter(tenantId, storeId, activeLetter);
    call
      .then((result) => { setLetterLock(result); flashToast(isLocked ? `✓ Letter ${activeLetter} unlocked` : `✓ Letter ${activeLetter} locked`); })
      .catch((error) => flashToast(error.message || 'Lock update failed', 'err'))
      .finally(() => setLockBusy(false));
  }

  // ── Finalise ──────────────────────────────────────────────────────────
  const [finalise, setFinalise] = useState(null);
  function openFinalise() {
    if (!activeLetter) return;
    setFinalise({ loading: true });
    api.getLabelLetterFinalise(tenantId, storeId, activeLetter)
      .then((data) => setFinalise({ data }))
      .catch((error) => setFinalise({ error: error.message || 'Could not load the finalise check' }));
  }
  function reviewFinaliseRows(codes, value) {
    if (!codes.length || isLocked || finalise?.busy) return;
    const codeSet = new Set(codes);
    setFinalise((cur) => ({ ...cur, busy: true }));
    const chunks = [];
    for (let i = 0; i < codes.length; i += 1000) chunks.push(codes.slice(i, i + 1000));
    chunks.reduce((p, chunk) => p.then(() => api.bulkSetLabelInclude(tenantId, storeId, chunk, value)), Promise.resolve())
      .then(() => {
        setRows((current) => current.map((row) => (codeSet.has(row.product_code) ? { ...row, include_label: value } : row)));
        setFinalise((cur) => {
          const counts = { ...cur.data.counts };
          counts.needs_review -= codes.length;
          counts.unreviewed -= codes.length;
          counts[value === 'Y' ? 'included' : 'excluded'] += codes.length;
          return { data: { ...cur.data, counts, needs_review: cur.data.needs_review.filter((r) => !codeSet.has(r.product_code)) } };
        });
        refreshLetterLock(activeLetter);
      })
      .catch((error) => { setFinalise((cur) => ({ ...cur, busy: false })); flashToast(error.message || '⚠ Review update failed', 'err'); });
  }
  function runFinalise() {
    if (!finalise?.data || finalise.busy) return;
    setFinalise((cur) => ({ ...cur, busy: true }));
    api.finaliseLabelLetter(tenantId, storeId, activeLetter)
      .then((report) => {
        setLetterLock(report.lock);
        setFinalise((cur) => ({ ...cur, busy: false, report }));
        flashToast(`✓ Letter ${report.letter} finalised and locked`);
        runSearch();
      })
      .catch((error) => { setFinalise((cur) => ({ ...cur, busy: false })); flashToast(error.message || '⚠ Finalise failed', 'err'); });
  }

  function exportCurrentLetterExcel() {
    if (!activeLetter || exportBusy) return;
    setExportBusy(true);
    api.exportLabelProductsExcel(tenantId, storeId, activeLetter)
      .then((blob) => {
        downloadBlob(blob, `label-exporter-${activeLetter}-${new Date().toISOString().slice(0, 10)}.xlsx`);
        flashToast(`✓ Exported letter ${activeLetter}`);
      })
      .catch((error) => flashToast(error.message || 'Export failed', 'err'))
      .finally(() => setExportBusy(false));
  }

  // ── Search ────────────────────────────────────────────────────────────
  function runSearch() {
    if (!tenantId || !storeId) {
      setStatus({ state: 'idle', message: 'Select a tenant/store in the header first.' });
      return;
    }
    const startsWithParam = Array.from(selectedLetters).join(',');
    setStatus({ state: 'loading', message: 'Loading products...' });
    const requestId = ++searchRequestRef.current;
    api.searchLabelProducts(tenantId, storeId, {
      q,
      startsWith: startsWithParam,
      unitDescription: selectedUnits.size ? Array.from(selectedUnits).join(',') : '',
      unitDescriptionMode: selectedUnits.size ? 'exact' : 'contains',
      unitSource,
      boxNumber,
      stockFilter,
      reviewStatus,
      onlyNullSublocation: boxNumber ? false : onlyNullSublocation,
      onlySaleUnitGtOne,
      sublocationFilter: selectedSublocs.size ? Array.from(selectedSublocs).join(',') : '',
    }).then((result) => {
      if (searchRequestRef.current !== requestId) return;
      const nextRows = asArray(result?.rows);
      setRows(nextRows);
      setActiveIndex(0);
      setSelectedCodes(new Set());
      setUnitOptions(asArray(result?.unit_descriptions));
      setUnitChoices(asArray(result?.unit_choices));
      setSublocOptions(asArray(result?.sublocations));
      const nextRemarks = {};
      nextRows.forEach((row) => { nextRemarks[row.product_code] = row.remarks || ''; });
      setRemarksDrafts(nextRemarks);
      setStatus({
        state: 'ok',
        message: nextRows.length ? `${nextRows.length} product(s).` : 'No products for this filter.',
      });
    }).catch((error) => {
      if (searchRequestRef.current !== requestId) return;
      setRows([]);
      setStatus({ state: 'error', message: error.message });
    });
  }

  function patchRow(productCode, patch) {
    setRows((current) => current.map((row) => (row.product_code === productCode ? { ...row, ...patch } : row)));
  }

  function resetFilters() {
    setQ('');
    setSelectedLetters(new Set());
    setSelectedUnits(new Set());
    setSelectedSublocs(new Set());
    setBoxNumber('');
    setStockFilter('all');
    setReviewStatus('');
    setOnlyNullSublocation(false);
    setOnlySaleUnitGtOne(false);
    setShowAdvanced(false);
    flashToast('✓ Filters reset');
  }

  // ── Review / unit / location editing ─────────────────────────────────
  function persistReview(row, nextValue, skipChecks = false) {
    if (isLocked) { flashToast(`⚠ Letter ${activeLetter} is locked`, 'err'); return; }
    if (row.include_label === nextValue) return;
    if (nextValue === 'Y' && !skipChecks && lblIsSaleUnitOneNotTab(row)) {
      setConfirm({
        title: `Include ${row.product_code} on the label?`,
        body: [`Sale unit is 1 but the unit is "${lblNewUnit(row) || '—'}", not TAB.`, 'Double-check this is really meant to be a single-piece label before including it.'],
        confirmLabel: 'Include anyway',
        onConfirm: () => { setConfirm(null); persistReview(row, nextValue, true); },
      });
      return;
    }
    if (nextValue === 'N' && !skipChecks && lblHasSellableStockMultiUnit(row)) {
      setConfirm({
        title: `Remove ${row.product_code} from the label list?`,
        body: [`Stock is available (${fmtQty(row.total_stock)} @ sale unit ${fmtQty(row.sale_unit)}).`, 'Do you want to remove this product from the label list?'],
        confirmLabel: 'Remove (mark N)',
        onConfirm: () => { setConfirm(null); persistReview(row, nextValue, true); },
      });
      return;
    }
    if (nextValue === 'Y' && lblIsStaleNoStock(row)) {
      flashToast(`⚠ ${row.product_code} — no transaction in the last 90 days`, 'err');
    }
    setSavingCode(row.product_code);
    api.updateLabelReview(tenantId, storeId, row.product_code, { include_label: nextValue })
      .then(() => { patchRow(row.product_code, { include_label: nextValue }); refreshLetterLock(activeLetter); })
      .catch((error) => setStatus({ state: 'error', message: error.message }))
      .finally(() => setSavingCode(''));
  }
  function cycleReview(row) {
    const next = row.include_label === 'Y' ? 'N' : row.include_label === 'N' ? null : 'Y';
    persistReview(row, next);
  }
  function saveRemarks(row) {
    if (isLocked) { flashToast(`⚠ Letter ${activeLetter} is locked`, 'err'); return; }
    const draft = (remarksDrafts[row.product_code] || '').trim();
    if (draft === (row.remarks || '')) return;
    setSavingCode(row.product_code);
    api.updateLabelReview(tenantId, storeId, row.product_code, { remarks: draft })
      .then(() => patchRow(row.product_code, { remarks: draft || null }))
      .catch((error) => setStatus({ state: 'error', message: error.message }))
      .finally(() => setSavingCode(''));
  }
  function commitUnit(row, value) {
    setEditingUnitCode(null);
    if (isLocked) { flashToast(`⚠ Letter ${activeLetter} is locked`, 'err'); return; }
    const next = String(value || '').trim().toUpperCase();
    const current = lblNewUnit(row).toUpperCase();
    if (!next || next === current) return;
    setSavingCode(row.product_code);
    api.correctLabelUnit(tenantId, storeId, row.product_code, next, lblOldUnit(row))
      .then(() => {
        patchRow(row.product_code, { corrected_unit: next, old_unit_description: row.old_unit_description || row.unit_description || null });
        setUnitChoices((prev) => (prev.includes(next) ? prev : [...prev, next]));
        flashToast(`✓ Unit → ${next}`);
      })
      .catch((error) => { setStatus({ state: 'error', message: error.message }); flashToast('⚠ Save failed', 'err'); })
      .finally(() => setSavingCode(''));
  }
  function commitLocation(row, value) {
    setEditingLocationCode(null);
    if (isLocked) { flashToast(`⚠ Letter ${activeLetter} is locked`, 'err'); return; }
    const next = String(value || '').trim().toUpperCase();
    const current = lblNewLoc(row).toUpperCase();
    if (!next || next === current) return;
    const capturedOld = lblNewLoc(row) || lblOldLoc(row);
    setSavingCode(row.product_code);
    api.correctLabelLocation(tenantId, storeId, row.product_code, next, capturedOld)
      .then(() => {
        patchRow(row.product_code, { assigned_sublocation: next, old_sublocation: row.old_sublocation || capturedOld || null, label_required: true });
        flashToast(`✓ Location → ${next}`);
      })
      .catch((error) => { setStatus({ state: 'error', message: error.message }); flashToast('⚠ Save failed', 'err'); })
      .finally(() => setSavingCode(''));
  }
  function clearLocationForRow(row) {
    if (isLocked) { flashToast(`⚠ Letter ${activeLetter} is locked`, 'err'); return; }
    setSavingCode(row.product_code);
    api.clearLabelAssignment(tenantId, storeId, [row.product_code])
      .then(() => { patchRow(row.product_code, { assigned_sublocation: null, assignment_type: null, label_required: false }); flashToast(`✓ Location cleared — ${row.product_code}`); })
      .catch((error) => { setStatus({ state: 'error', message: error.message }); flashToast('⚠ Clear failed', 'err'); })
      .finally(() => setSavingCode(''));
  }
  function toggleSelect(code) {
    setSelectedCodes((current) => {
      const next = new Set(current);
      if (next.has(code)) next.delete(code); else next.add(code);
      return next;
    });
  }

  // ── Bulk mark / auto dead-stock N / unit replace ────────────────────
  function bulkMark(value, skipStockCheck = false) {
    if (!rows.length || bulkBusy) return;
    if (isLocked) { flashToast(`⚠ Letter ${activeLetter} is locked`, 'err'); return; }
    if (value === 'N' && !skipStockCheck) {
      const withStock = rows.filter(lblHasSellableStockMultiUnit);
      if (withStock.length > 0) {
        setConfirm({
          title: `Remove ${withStock.length} product(s) with stock available from the label list?`,
          body: [`${withStock.length} of ${rows.length} loaded product(s) have sale unit > 1 and stock on hand.`, 'Do you want to remove these from the label list by marking all N?'],
          confirmLabel: 'Mark all N',
          onConfirm: () => { setConfirm(null); bulkMark(value, true); },
        });
        return;
      }
    }
    const codes = rows.map((row) => row.product_code);
    const codeSet = new Set(codes);
    const staleCount = value === 'Y' ? rows.filter(lblIsStaleNoStock).length : 0;
    const oddUnitCount = value === 'Y' ? rows.filter(lblIsSaleUnitOneNotTab).length : 0;
    setBulkBusy(true);
    api.bulkSetLabelInclude(tenantId, storeId, codes, value)
      .then(() => {
        setRows((current) => current.map((row) => (codeSet.has(row.product_code) ? { ...row, include_label: value } : row)));
        flashToast(`✓ ${codes.length} marked ${value}`);
        if (staleCount > 0) flashToast(`⚠ ${staleCount} marked Y had no transaction in the last 90 days`, 'err');
        if (oddUnitCount > 0) flashToast(`⚠ ${oddUnitCount} marked Y have sale unit 1 but unit isn't TAB`, 'err');
        refreshLetterLock(activeLetter);
      })
      .catch((error) => { setStatus({ state: 'error', message: error.message }); flashToast('⚠ Bulk update failed', 'err'); })
      .finally(() => setBulkBusy(false));
  }
  function autoMarkStaleN() {
    if (!rows.length || bulkBusy) return;
    if (isLocked) { flashToast(`⚠ Letter ${activeLetter} is locked`, 'err'); return; }
    const targets = rows.filter((row) => !row.include_label && lblIsStaleNoStock(row));
    if (!targets.length) { flashToast('No unreviewed dead-stock products to mark'); return; }
    const codes = targets.map((row) => row.product_code);
    const codeSet = new Set(codes);
    setBulkBusy(true);
    api.bulkSetLabelInclude(tenantId, storeId, codes, 'N')
      .then(() => {
        setRows((current) => current.map((row) => (codeSet.has(row.product_code) ? { ...row, include_label: 'N' } : row)));
        flashToast(`✓ ${codes.length} unreviewed dead-stock product(s) auto-marked N`);
        refreshLetterLock(activeLetter);
      })
      .catch((error) => { setStatus({ state: 'error', message: error.message }); flashToast('⚠ Bulk update failed', 'err'); })
      .finally(() => setBulkBusy(false));
  }
  const [unitReplace, setUnitReplace] = useState(null);
  function openUnitReplace() {
    if (!rows.length) return;
    const seed = rows[activeIndex] ? lblNewUnit(rows[activeIndex]) : lblNewUnit(rows[0]);
    setUnitReplace({ from: (seed || '').toUpperCase(), to: 'TAB' });
  }
  const unitReplaceMatches = useMemo(() => {
    const from = (unitReplace?.from || '').trim().toUpperCase();
    if (!from) return [];
    return rows.filter((row) => lblNewUnit(row).toUpperCase() === from);
  }, [unitReplace, rows]);
  function applyUnitReplace() {
    const to = (unitReplace?.to || '').trim().toUpperCase();
    if (!to) { flashToast('Enter a replacement unit', 'err'); return; }
    const codes = unitReplaceMatches.map((row) => row.product_code);
    if (!codes.length) { flashToast('No loaded rows match', 'err'); return; }
    const codeSet = new Set(codes);
    setBulkBusy(true);
    api.bulkCorrectLabelUnit(tenantId, storeId, codes, to)
      .then(() => {
        setRows((current) => current.map((row) => {
          if (!codeSet.has(row.product_code)) return row;
          const oldMaster = row.old_unit_description || row.unit_description || null;
          return { ...row, corrected_unit: to, old_unit_description: oldMaster };
        }));
        flashToast(`✓ ${codes.length} → ${to}`);
        setUnitReplace(null);
      })
      .catch((error) => { setStatus({ state: 'error', message: error.message }); flashToast('⚠ Replace failed', 'err'); })
      .finally(() => setBulkBusy(false));
  }

  // ── Clear actions (confirmed, super-admin) ──────────────────────────
  function requestClearAssignment() {
    const codes = rows.map((r) => r.product_code);
    const codeSet = new Set(codes);
    const nAssigned = rows.filter((r) => lblIsAssigned(r)).length;
    if (!codes.length) return;
    setConfirm({
      title: 'Clear assignment state?',
      body: [`Reset location assignment for ${codes.length} loaded product(s) (${nAssigned} currently assigned).`, 'This clears: assigned box, pending/assigned status and label-queue state.', 'It will NOT change: Y/N review, OLD LOCATION, unit correction, or any master/product data.'],
      confirmLabel: 'Clear Assignment State',
      onConfirm: () => {
        setBulkBusy(true);
        api.clearLabelAssignment(tenantId, storeId, codes)
          .then(() => { setRows((cur) => cur.map((r) => (codeSet.has(r.product_code) ? { ...r, assigned_sublocation: null, assignment_type: null, label_required: false } : r))); flashToast(`✓ Assignment cleared (${codes.length})`); })
          .catch((error) => { setStatus({ state: 'error', message: error.message }); flashToast('⚠ Clear failed', 'err'); })
          .finally(() => { setBulkBusy(false); setConfirm(null); });
      },
    });
  }
  function requestClearNewLocation() {
    const targets = rows.filter((r) => lblIsAutoBoxLoc(r));
    const codes = targets.map((r) => r.product_code);
    const codeSet = new Set(codes);
    if (!codes.length) { flashToast('No auto-box (letter+0, e.g. A001) locations in view', 'err'); return; }
    setConfirm({
      title: `Clear new location for ${codes.length} product(s)?`,
      body: [`Reset the NEW LOCATION (box) to blank for ${codes.length} product(s) whose box is auto-assigned (e.g. A001).`, 'Named/hand-picked locations like "Counter", "SYP A" are KEPT.', 'It will NOT change: Y/N review, OLD LOCATION, unit correction, or master data.'],
      confirmLabel: 'Clear New Location',
      onConfirm: () => {
        setBulkBusy(true);
        api.clearLabelAssignment(tenantId, storeId, codes)
          .then(() => { setRows((cur) => cur.map((r) => (codeSet.has(r.product_code) ? { ...r, assigned_sublocation: null, assignment_type: null, label_required: false } : r))); flashToast(`✓ New location cleared (${codes.length})`); })
          .catch((error) => { setStatus({ state: 'error', message: error.message }); flashToast('⚠ Clear failed', 'err'); })
          .finally(() => { setBulkBusy(false); setConfirm(null); });
      },
    });
  }
  function requestClearReview() {
    const codes = rows.map((r) => r.product_code);
    const codeSet = new Set(codes);
    if (!codes.length) return;
    setConfirm({
      title: `Reset review for ${codes.length} loaded product(s)?`,
      body: ['This will clear: Y / N review state, pending assignment state, and current label-queue state.', 'It will NOT delete: product master data, OLD LOCATION, sales, purchase or stock.'],
      confirmLabel: 'Reset Review',
      onConfirm: () => {
        setBulkBusy(true);
        api.clearLabelReview(tenantId, storeId, codes)
          .then(() => {
            setRows((cur) => cur.map((r) => (codeSet.has(r.product_code) ? { ...r, include_label: null, assigned_sublocation: null, assignment_type: null, label_required: false } : r)));
            setSelectedCodes((cur) => new Set(Array.from(cur).filter((c) => !codeSet.has(c))));
            flashToast(`✓ Review reset (${codes.length})`);
          })
          .catch((error) => { setStatus({ state: 'error', message: error.message }); flashToast('⚠ Reset failed', 'err'); })
          .finally(() => { setBulkBusy(false); setConfirm(null); });
      },
    });
  }

  // ── Box assignment drawer ───────────────────────────────────────────
  const assignTargets = useMemo(() => {
    const yRows = rows.filter((row) => row.include_label === 'Y');
    if (!selectedCodes.size) return yRows;
    return yRows.filter((row) => selectedCodes.has(row.product_code));
  }, [rows, selectedCodes]);
  const assignLetterCounts = useMemo(() => {
    const counts = {};
    assignTargets.forEach((row) => {
      const c = String(row.product_name || '').trim().charAt(0).toUpperCase();
      if (/[A-Z]/.test(c)) counts[c] = (counts[c] || 0) + 1;
    });
    return counts;
  }, [assignTargets]);
  const assignLetters = useMemo(() => Object.keys(assignLetterCounts).sort(), [assignLetterCounts]);

  const [assignOpen, setAssignOpen] = useState(false);
  const [assignForm, setAssignForm] = useState({ unit: '', letterModes: {} });
  const [assignPreview, setAssignPreview] = useState(null);
  const [assignBusy, setAssignBusy] = useState(false);
  const [assignError, setAssignError] = useState('');
  const assignUnitIsSyp = (assignForm.unit || '').trim().toUpperCase() === 'SYP';

  function openAssignDrawer() {
    if (!assignTargets.length) { setStatus({ state: 'error', message: 'Mark products Y before assigning locations.' }); return; }
    const first = assignTargets[0];
    const unit = (first.corrected_unit || first.unit_description || '').toUpperCase();
    const letterModes = {};
    Object.keys(assignLetterCounts).forEach((L) => { letterModes[L] = { mode: 'continue', startNumber: 1 }; });
    setAssignForm({ unit, letterModes });
    setAssignPreview(null);
    setAssignError('');
    setAssignOpen(true);
  }
  function setLetterMode(letter, patch) {
    setAssignForm((f) => ({ ...f, letterModes: { ...f.letterModes, [letter]: { ...(f.letterModes[letter] || { mode: 'continue', startNumber: 1 }), ...patch } } }));
    setAssignPreview(null);
  }
  function setAllLetterModes(mode) {
    setAssignForm((f) => {
      const letterModes = {};
      assignLetters.forEach((L) => { letterModes[L] = { ...(f.letterModes[L] || { startNumber: 1 }), mode }; });
      return { ...f, letterModes };
    });
    setAssignPreview(null);
  }
  function assignBody() {
    const unit = (assignForm.unit || '').trim().toUpperCase();
    const letterPlans = unit === 'SYP' ? [] : assignLetters.map((L) => {
      const m = assignForm.letterModes[L] || { mode: 'continue', startNumber: 1 };
      return { letter: L, mode: m.mode, start_number: Number(m.startNumber) || 1 };
    });
    return {
      unit,
      assignment_type: 'standard_box',
      letter: assignLetters[0] || '',
      mode: 'continue',
      start_number: 1,
      product_codes: assignTargets.map((row) => row.product_code),
      letter_plans: letterPlans,
    };
  }
  function runPreview() {
    setAssignBusy(true);
    setAssignError('');
    api.previewLabelAssignment(tenantId, storeId, assignBody())
      .then((result) => setAssignPreview(result))
      .catch((error) => { setAssignPreview(null); setAssignError(error.message); })
      .finally(() => setAssignBusy(false));
  }
  function runCommit() {
    setAssignBusy(true);
    setAssignError('');
    api.commitLabelAssignment(tenantId, storeId, assignBody())
      .then((result) => {
        const codes = new Set((result?.assignments || []).map((a) => a.product_code));
        setRows((current) => current.map((row) => (codes.has(row.product_code)
          ? { ...row, assigned_sublocation: (result.assignments.find((a) => a.product_code === row.product_code) || {}).box, label_required: true }
          : row)));
        setStatus({ state: 'ok', message: `Assigned ${result?.assigned_count ?? codes.size} product(s) to ${result?.boxes?.length ?? 0} box(es).` });
        setAssignOpen(false);
        setSelectedCodes(new Set());
      })
      .catch((error) => setAssignError(error.message))
      .finally(() => setAssignBusy(false));
  }

  // ── Label queue ──────────────────────────────────────────────────────
  const [queueOpen, setQueueOpen] = useState(false);
  const [queueRows, setQueueRows] = useState([]);
  const [queueBusy, setQueueBusy] = useState(false);
  const [queuePrintFilter, setQueuePrintFilter] = useState('all');
  const [queueLetterSel, setQueueLetterSel] = useState(() => new Set());
  const [pdfBusy, setPdfBusy] = useState(false);
  const [queueClearBusy, setQueueClearBusy] = useState(false);

  function openQueue() {
    setQueueOpen(true);
    setQueueBusy(true);
    setQueuePrintFilter('all');
    setQueueLetterSel(new Set());
    api.getLabelQueue(tenantId, storeId)
      .then((result) => setQueueRows(asArray(result?.rows)))
      .catch((error) => setStatus({ state: 'error', message: error.message }))
      .finally(() => setQueueBusy(false));
  }
  const queueLetters = useMemo(() => {
    const set = new Set();
    queueRows.forEach((r) => { const L = queueLocationLetter(r.location); if (L) set.add(L); });
    return Array.from(set).sort();
  }, [queueRows]);
  const filteredQueueRows = useMemo(() => queueRows.filter((r) => (
    (queuePrintFilter === 'ready' ? !r.label_created_at : queuePrintFilter === 'printed' ? !!r.label_created_at : true)
    && (!queueLetterSel.size || queueLetterSel.has(queueLocationLetter(r.location)))
  )), [queueRows, queuePrintFilter, queueLetterSel]);

  function escapeHtml(text) {
    return String(text).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }
  function printQueue() {
    if (!filteredQueueRows.length) return;
    const win = window.open('', '_blank');
    if (!win) return;
    const body = filteredQueueRows.map((r) => `
      <div class="lbl">
        <div class="nm">${escapeHtml(r.product_name || '')}</div>
        <div class="mt"><span>${escapeHtml(r.location || '')}</span><span>${escapeHtml(r.unit_description || '')}</span></div>
        <div class="mr">MRP ₹${escapeHtml(String(r.mrp ?? ''))}</div>
      </div>`).join('\n');
    win.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>Labels</title><style>
      *{box-sizing:border-box;margin:0;padding:0}body{font-family:Arial,sans-serif;display:flex;flex-wrap:wrap;gap:2mm;padding:4mm}
      .lbl{width:50mm;height:25mm;border:0.4px solid #000;padding:1.5mm;display:flex;flex-direction:column;justify-content:center;page-break-inside:avoid}
      .nm{font-weight:700;font-size:9pt;line-height:1.15;overflow:hidden}.mt{display:flex;justify-content:space-between;font-size:8pt;margin-top:1mm}.mr{font-weight:600;font-size:8pt;margin-top:auto}
      @page{margin:5mm}</style></head><body>${body}</body></html>`);
    win.document.close();
    win.focus();
    setTimeout(() => win.print(), 400);
    api.markLabelsPrinted(tenantId, storeId, filteredQueueRows.map((r) => r.product_code))
      .then(() => setQueueRows((current) => current.map((r) => ({ ...r, label_created_at: r.label_created_at || 'printed' }))))
      .catch(() => {});
  }
  function exportQueuePdf() {
    if (!filteredQueueRows.length || pdfBusy) return;
    setPdfBusy(true);
    const letters = Array.from(queueLetterSel).sort();
    const activeStore = stores.find((s) => s.store_id === storeId);
    const fileName = `label-queue-${activeStore?.store_code || 'store'}-${letters.length ? letters.join('') : 'all'}-a3-${new Date().toISOString().slice(0, 10)}.pdf`;
    api.exportLabelQueuePdf(tenantId, storeId, letters.join(','))
      .then((blob) => {
        downloadBlob(blob, fileName);
        return api.markLabelsPrinted(tenantId, storeId, filteredQueueRows.map((r) => r.product_code));
      })
      .then(() => setQueueRows((current) => current.map((r) => ({ ...r, label_created_at: r.label_created_at || 'printed' }))))
      .catch((error) => setStatus({ state: 'error', message: error.message }))
      .finally(() => setPdfBusy(false));
  }
  function clearPrintedInView() {
    const codes = filteredQueueRows.filter((r) => r.label_created_at).map((r) => r.product_code);
    if (!codes.length) return;
    const codeSet = new Set(codes);
    setConfirm({
      title: `Clear printed status for ${codes.length} label(s)?`,
      body: ['This resets the Printed mark so they show as Ready to print again.', 'It will NOT change the assigned box/location — only the print stamp.'],
      confirmLabel: 'Clear Printed',
      onConfirm: () => {
        setQueueClearBusy(true);
        api.clearPrintedLabels(tenantId, storeId, codes)
          .then(() => { setQueueRows((current) => current.map((r) => (codeSet.has(r.product_code) ? { ...r, label_created_at: null } : r))); flashToast(`✓ Printed status cleared (${codes.length})`); })
          .catch((error) => { setStatus({ state: 'error', message: error.message }); flashToast('⚠ Clear failed', 'err'); })
          .finally(() => { setQueueClearBusy(false); setConfirm(null); });
      },
    });
  }

  const remarksOptions = useMemo(() => {
    const used = rows.map((row) => row.remarks).filter(Boolean);
    return Array.from(new Set([...LABEL_REMARKS_PRESETS, ...used]));
  }, [rows]);

  const progress = useMemo(() => {
    const c = { total: rows.length, reviewed: 0, included: 0, excluded: 0, remaining: 0, pending: 0, assigned: 0 };
    for (const row of rows) {
      const rv = lblReview(row);
      if (rv === 'NOT_REVIEWED') { c.remaining += 1; continue; }
      c.reviewed += 1;
      if (rv === 'EXCLUDED') { c.excluded += 1; continue; }
      c.included += 1;
      if (lblAssignment(row) === 'ASSIGNED') c.assigned += 1; else c.pending += 1;
    }
    c.pct = c.total ? Math.round((c.reviewed / c.total) * 100) : 0;
    return c;
  }, [rows]);

  // ── Product intelligence (trend / purchase / sales) side panel ─────
  const activeRow = rows[activeIndex] || null;
  const [trendRows, setTrendRows] = useState([]);
  const [purchaseRows, setPurchaseRows] = useState([]);
  const [saleRows, setSaleRows] = useState([]);
  const [intelLoading, setIntelLoading] = useState(false);
  const intelRequestRef = useRef(0);

  useEffect(() => {
    if (!activeRow?.product_code || !tenantId || !storeId) {
      setTrendRows([]); setPurchaseRows([]); setSaleRows([]);
      return;
    }
    const requestId = ++intelRequestRef.current;
    setIntelLoading(true);
    Promise.all([
      api.getLabelProductTrend(tenantId, storeId, activeRow.product_code).catch(() => ({ rows: [] })),
      api.getLabelProductPurchases(tenantId, storeId, activeRow.product_code).catch(() => ({ rows: [] })),
      api.getLabelProductSales(tenantId, storeId, activeRow.product_code).catch(() => ({ rows: [] })),
    ]).then(([trend, purchases, sales]) => {
      if (intelRequestRef.current !== requestId) return;
      setTrendRows(asArray(trend?.rows));
      setPurchaseRows(asArray(purchases?.rows));
      setSaleRows(asArray(sales?.rows));
    }).finally(() => {
      if (intelRequestRef.current !== requestId) return;
      setIntelLoading(false);
    });
  }, [activeRow?.product_code, tenantId, storeId]);

  function renderCell(col, row, index) {
    const code = row.product_code;
    const selected = selectedCodes.has(code);
    switch (col.key) {
      case 'sno':
        return <td key="sno" className="lblx-num lblx-sno" onClick={(e) => { e.stopPropagation(); toggleSelect(code); }}>{selected ? '✓' : index + 1}</td>;
      case 'code':
        return <td key="code" className="lblx-code">{row.product_code}</td>;
      case 'product':
        return <td key="product" className="lblx-grow" title={row.product_name}>{row.product_name}</td>;
      case 'oldUnit':
        return <td key="oldUnit">{lblOldUnit(row) || '—'}</td>;
      case 'newUnit': {
        const oldUnit = lblOldUnit(row);
        const newUnit = lblNewUnit(row);
        const changed = lblUnitChanged(row);
        return (
          <td key="newUnit" onClick={(e) => e.stopPropagation()}>
            {editingUnitCode === code ? (
              <EditCombo
                current={newUnit}
                options={Array.from(new Set([...LABEL_UNIT_PRESETS, ...unitChoices, ...unitOptions])).sort()}
                onPick={(value) => commitUnit(row, value)}
                onCancel={() => setEditingUnitCode(null)}
                placeholder="Search / type unit…"
              />
            ) : (
              <button type="button" className={`lblx-chip ${changed ? 'is-changed' : ''}`} disabled={savingCode === code || isLocked}
                title={isLocked ? `Letter ${activeLetter} is locked` : changed ? `Corrected from ${oldUnit} — click to change` : 'Click to correct unit'}
                onClick={() => { setActiveIndex(index); setEditingUnitCode(code); }}>
                {newUnit || '—'}
              </button>
            )}
          </td>
        );
      }
      case 'saleUnit':
        return <td key="saleUnit" className="lblx-num">{fmtQty(row.sale_unit)}</td>;
      case 'oldLoc':
        return <td key="oldLoc">{lblOldLoc(row) || <span className="lblx-null">—</span>}</td>;
      case 'newLoc': {
        const newLoc = lblNewLoc(row);
        return (
          <td key="newLoc" onClick={(e) => e.stopPropagation()}>
            {editingLocationCode === code ? (
              <EditCombo current={newLoc} options={locationOptions} onPick={(value) => commitLocation(row, value)} onCancel={() => setEditingLocationCode(null)} placeholder="Search / type location…" />
            ) : (
              <>
                <button type="button" className="lblx-chip" disabled={savingCode === code || isLocked}
                  title={isLocked ? `Letter ${activeLetter} is locked` : newLoc ? `Manually move from ${newLoc}` : 'Click to assign a location'}
                  onClick={() => { setActiveIndex(index); setEditingLocationCode(code); }}>
                  {newLoc || <span className="lblx-null">—</span>}
                </button>
                {admin && newLoc && (
                  <button type="button" className="lblx-chip-clear" disabled={savingCode === code || isLocked}
                    title={isLocked ? `Letter ${activeLetter} is locked` : "Unassign — clear this product's location"}
                    onClick={() => { setActiveIndex(index); clearLocationForRow(row); }}>×</button>
                )}
              </>
            )}
          </td>
        );
      }
      case 'stock':
        return <td key="stock" className={`lblx-num ${Number(row.total_stock) === 0 ? 'is-zero' : ''}`}>{fmtQty(row.total_stock)}</td>;
      case 'lpd':
        return <td key="lpd" className="lblx-num" title={row.last_purchase_date ? `Last purchase: ${fmtDate(row.last_purchase_date)}` : 'Never purchased'}>{fmtDays(row.purchase_days, row.last_purchase_date)}</td>;
      case 'lsd':
        return <td key="lsd" className="lblx-num" title={row.last_sale_date ? `Last sale: ${fmtDate(row.last_sale_date)}` : 'Never sold'}>{fmtDays(row.sale_days, row.last_sale_date)}</td>;
      case 'review': {
        const review = row.include_label || null;
        const badge = review === 'Y' ? 'Y' : review === 'N' ? 'N' : '—';
        const cls = review === 'Y' ? 'is-yes' : review === 'N' ? 'is-no' : 'is-none';
        return (
          <td key="review" className="lblx-review-cell">
            <button type="button" className={`lblx-review-badge ${cls}`} disabled={savingCode === code || isLocked}
              title={isLocked ? `Letter ${activeLetter} is locked` : 'Click to cycle —/Y/N'}
              onClick={(e) => { e.stopPropagation(); cycleReview(row); }}>{badge}</button>
          </td>
        );
      }
      default:
        return <td key={col.key} />;
    }
  }

  const locationOptions = useMemo(() => {
    const used = rows.map((row) => lblNewLoc(row)).filter(Boolean);
    return Array.from(new Set(used)).sort();
  }, [rows]);

  return (
    <PageLayout title="Label Export" dense>
      <div className="lblx-filterbar">
        <label className="lblx-field">
          <span>Letter</span>
          <MultiPicker options={LABEL_LETTER_OPTIONS} selected={selectedLetters} onChange={setSelectedLetters} placeholder="Any letter" noun="letter" />
        </label>

        <label className="lblx-field lblx-search">
          <span>Search</span>
          <input
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); runSearch(); } }}
            placeholder="Product name or code — press Enter or Search"
          />
        </label>

        <label className="lblx-field" title={unitSource === 'old' ? 'Filters by the original (master) unit' : "Filters by the effective (corrected) unit"}>
          <span>
            Unit
            <span className="lblx-unit-toggle">
              <button type="button" className={unitSource === 'new' ? 'is-active' : ''} onClick={() => { if (unitSource !== 'new') { setUnitSource('new'); setSelectedUnits(new Set()); } }}>New</button>
              <button type="button" className={unitSource === 'old' ? 'is-active' : ''} onClick={() => { if (unitSource !== 'old') { setUnitSource('old'); setSelectedUnits(new Set()); } }}>Old</button>
            </span>
          </span>
          <MultiPicker options={unitOptions} selected={selectedUnits} onChange={setSelectedUnits} placeholder="Any unit" noun="unit" />
        </label>

        <label className="lblx-field">
          <span>Review</span>
          <select value={reviewStatus} onChange={(e) => setReviewStatus(e.target.value)}>
            <option value="">All</option>
            <option value="unreviewed">Unreviewed</option>
            <option value="Y">Included (Y)</option>
            <option value="N">Excluded (N)</option>
          </select>
        </label>

        <label className="lblx-field">
          <span>Stock</span>
          <select value={stockFilter} onChange={(e) => setStockFilter(e.target.value)}>
            {LABEL_STOCK_FILTERS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </label>

        <span className="lblx-filterspace" />

        <div className="lblx-filteractions">
          {status.state === 'loading' && <span className="lblx-searching">Searching…</span>}
          <button type="button" className={`ntm-button ${showAdvanced ? 'is-on' : ''}`} onClick={() => setShowAdvanced((v) => !v)}>Advanced {showAdvanced ? '▲' : '▾'}</button>
          <button type="button" className="ntm-button ntm-button--primary" onClick={runSearch} disabled={status.state === 'loading' || !tenantId || !storeId}>Search</button>
          <button type="button" className="ntm-button" onClick={resetFilters} disabled={status.state === 'loading'}>Reset</button>
        </div>
      </div>

      {showAdvanced && (
        <div className="lblx-filterbar">
          <label className="lblx-field">
            <span>Old Loc</span>
            <MultiPicker options={sublocOptions} selected={selectedSublocs} onChange={setSelectedSublocs} placeholder="Any location" noun="location" />
          </label>
          <label className="lblx-field">
            <span>Box</span>
            <input value={boxNumber} onChange={(e) => setBoxNumber(e.target.value.toUpperCase())} placeholder="Any box" />
          </label>
          <label className="lblx-check">
            <input type="checkbox" checked={onlyNullSublocation} disabled={!!boxNumber} onChange={(e) => setOnlyNullSublocation(e.target.checked)} />
            <span>Subloc null</span>
          </label>
          <label className="lblx-check">
            <input type="checkbox" checked={onlySaleUnitGtOne} onChange={(e) => setOnlySaleUnitGtOne(e.target.checked)} />
            <span>Sale &gt;1</span>
          </label>
        </div>
      )}

      <div className="lblx-actionbar">
        <button type="button" className="ntm-button" disabled={!rows.length || bulkBusy || isLocked} onClick={() => bulkMark('Y')}>Mark all Y</button>
        <button type="button" className="ntm-button" disabled={!rows.length || bulkBusy || isLocked} onClick={() => bulkMark('N')}>Mark all N</button>
        <button type="button" className="ntm-button" disabled={!rows.length || bulkBusy || isLocked} onClick={autoMarkStaleN} title="Mark N only still-unreviewed, zero-stock, dead rows">Mark Dead Stock N</button>
        <button type="button" className="ntm-button" disabled={!rows.length || bulkBusy || isLocked} onClick={openUnitReplace} title="Find a unit and replace it (e.g. RM → TAB)">Replace Unit…</button>
        {admin && (
          <button type="button" className="ntm-button" disabled={!assignTargets.length || isLocked} onClick={openAssignDrawer} title="Assign locations to reviewed-Y products">
            Assign Locations{assignTargets.length ? ` (${assignTargets.length})` : ''}
          </button>
        )}
        <button type="button" className="ntm-button" onClick={openQueue}>Label Queue</button>
        <button type="button" className="ntm-button ntm-button--primary" disabled={!activeLetter || exportBusy} onClick={exportCurrentLetterExcel} title={activeLetter ? `Export letter ${activeLetter}` : 'Pick exactly one letter'}>
          {exportBusy ? 'Exporting…' : 'Export to Excel'}
        </button>
        {isLocked ? (
          admin && <button type="button" className="ntm-button is-locked" disabled={lockBusy} onClick={toggleLetterLock} title={`Letter ${activeLetter} is locked — click to unlock`}>{lockBusy ? '…' : '🔒 Locked'}</button>
        ) : (
          <button type="button" className="ntm-button" disabled={!activeLetter} onClick={openFinalise} title={!activeLetter ? 'Pick exactly one letter' : `Finalise letter ${activeLetter}`}>✔ Finalise…</button>
        )}
        {activeLetter && letterLock?.letter === activeLetter && !isLocked && (letterLock?.unreviewed_count || 0) > 0 && (
          <span className="lblx-unreviewed-warn">{letterLock.unreviewed_count} unreviewed</span>
        )}
        {activeLetter && letterLock?.letter === activeLetter && letterLock?.last_edit && (
          <span className="lblx-last-edit">Last edit: {fmtDateTime(letterLock.last_edit)}</span>
        )}
        {admin && (
          <span className="lblx-clear-group">
            <button type="button" className="ntm-button" disabled={!rows.length || bulkBusy} onClick={requestClearAssignment}>Clear Assignment…</button>
            <button type="button" className="ntm-button" disabled={!rows.length || bulkBusy} onClick={requestClearNewLocation}>Clear New Loc…</button>
            <button type="button" className="ntm-button" disabled={!rows.length || bulkBusy} onClick={requestClearReview}>Clear Review…</button>
          </span>
        )}
        <span className="lblx-spacer" />
        <div className="lblx-colsettings" ref={colSettingsRef}>
          <button type="button" className="ntm-button" onClick={() => setColSettingsOpen((v) => !v)}>Columns</button>
          {colSettingsOpen && (
            <div className="lblx-colsettings-panel">
              <div className="lblx-colsettings-header">
                <span>Columns</span>
                <button type="button" className="lblx-colsettings-reset" onClick={() => setHidden(new Set())}>Reset</button>
              </div>
              {LABEL_COLUMNS.map((c) => (
                <label key={c.key} className="lblx-colsettings-row">
                  <input type="checkbox" checked={!hidden.has(c.key)} disabled={c.locked}
                    onChange={() => setHidden((cur) => { const next = new Set(cur); if (next.has(c.key)) next.delete(c.key); else next.add(c.key); return next; })} />
                  {c.label}
                </label>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="lblx-statusbar">
        <span className="lblx-kbd">Click Review to cycle —/Y/N</span>
        <span className="lblx-progress">
          {rows.length > 0 ? (
            <>
              <b>{progress.total}</b> Total
              <i>·</i> <b>{progress.reviewed}</b> Reviewed
              <i>·</i> <b className="is-y">{progress.included}</b> Incl
              <i>·</i> <b className="is-n">{progress.excluded}</b> Excl
              <i>·</i> <b>{progress.remaining}</b> Remaining
              <i>·</i> <b>{progress.pending}</b> Pending
              <i>·</i> <b>{progress.assigned}</b> Assigned
              <span className="lblx-progbar"><span style={{ width: `${progress.pct}%` }} /></span>
            </>
          ) : (
            <span className={`lblx-msg lblx-msg-${status.state}`}>
              {status.message}
              {status.state === 'error' && <button type="button" className="lblx-retry" onClick={runSearch}>Retry</button>}
            </span>
          )}
        </span>
        {!admin && <span className="lblx-note">Review only — assignment is super-admin</span>}
        {selectedCodes.size > 0 && <span className="lblx-sel">{selectedCodes.size} selected</span>}
        {storeName && <span className="lblx-note">{storeName}{!canChangeStore ? '' : ''}</span>}
      </div>

      <div className="lblx-body">
        <div className="lblx-main">
          <div className="lblx-tablewrap">
            <table className="lblx-table">
              <thead>
                <tr>
                  {visibleCols.map((c) => <th key={c.key} style={{ width: c.width }}>{c.label}</th>)}
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 ? (
                  <tr>
                    <td colSpan={visibleCols.length} className="lblx-empty">
                      {status.state === 'loading' ? 'Loading products…' : status.state === 'error' ? (
                        <span>Unable to load products. {status.message} <button type="button" className="lblx-retry" onClick={runSearch}>Retry</button></span>
                      ) : 'Pick a letter, then Search to load products.'}
                    </td>
                  </tr>
                ) : rows.map((row, index) => {
                  const code = row.product_code;
                  const selected = selectedCodes.has(code);
                  return (
                    <tr key={code}
                      className={`${index === activeIndex ? 'is-active' : ''} ${selected ? 'is-picked' : ''} ${row.include_label === 'Y' ? 'is-y' : row.include_label === 'N' ? 'is-n' : ''}`}
                      onClick={() => setActiveIndex(index)}>
                      {visibleCols.map((col) => renderCell(col, row, index))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <datalist id="lblx-remarks-options">
              {remarksOptions.map((option) => <option key={option} value={option} />)}
            </datalist>
          </div>
        </div>

        <aside className="lblx-side">
          <div className="lblx-side-head">
            {activeRow ? (
              <>
                <div className="lblx-side-titlerow">
                  <strong title={activeRow.product_name}>{activeRow.product_name}</strong>
                  <span className={`lblx-side-review ${activeRow.include_label === 'Y' ? 'is-yes' : activeRow.include_label === 'N' ? 'is-no' : 'is-none'}`}>
                    {activeRow.include_label === 'Y' ? 'Y' : activeRow.include_label === 'N' ? 'N' : '—'}
                  </span>
                </div>
                <div className="lblx-side-evidence">
                  <span>Sale <b>{activeRow.last_sale_date ? `${activeRow.sale_days}d` : '—'}</b></span>
                  <span className="lblx-side-sep">·</span>
                  <span>Purchase <b>{activeRow.last_purchase_date ? `${activeRow.purchase_days}d` : '—'}</b></span>
                </div>
                <div className="lblx-side-context">
                  Stock <b className={Number(activeRow.total_stock) === 0 ? 'is-zero' : undefined}>{fmtQty(activeRow.total_stock)}</b>
                  {' · '}{lblNewUnit(activeRow) || '—'}
                  {' · '}{lblNewLoc(activeRow) || lblOldLoc(activeRow) || 'Unassigned'}
                </div>
                <label className="lblx-side-remarks">
                  <span>Remarks</span>
                  <input
                    list="lblx-remarks-options"
                    value={remarksDrafts[activeRow.product_code] ?? ''}
                    disabled={savingCode === activeRow.product_code}
                    placeholder="Counter, SYP, unit fix…"
                    onChange={(e) => setRemarksDrafts((current) => ({ ...current, [activeRow.product_code]: e.target.value }))}
                    onBlur={() => saveRemarks(activeRow)}
                  />
                </label>
              </>
            ) : <span className="lblx-side-hint">Select a product to see its trend, purchase &amp; sales.</span>}
          </div>

          {activeRow && (
            <>
              <section className="lblx-panel">
                <div className="lblx-panel-title">Monthly Trend{intelLoading && <span> …</span>}</div>
                <div className="lblx-panel-body lblx-trend">
                  {!trendRows.length ? <div className="lblx-empty-mini">{intelLoading ? 'Loading…' : 'No monthly statistics.'}</div> : (
                    <table className="lblx-intel-table">
                      <thead><tr><th>Month</th><th className="lblx-num">Purchase</th><th className="lblx-num">Sale</th><th className="lblx-num">Stock</th><th className="lblx-num">Adj</th></tr></thead>
                      <tbody>
                        {trendRows.slice(0, 6).map((row, i) => (
                          <tr key={i}>
                            <td>{row.month}</td>
                            <td className="lblx-num">{fmtQty((Number(row.purchase_qty) || 0) + (Number(row.transfer_in_qty) || 0))}</td>
                            <td className="lblx-num">{fmtQty((Number(row.sale_qty) || 0) + (Number(row.transfer_out_qty) || 0))}</td>
                            <td className="lblx-num">{fmtQty(row.stock_in_hand)}</td>
                            <td className="lblx-num">{fmtQty(row.adjustment_qty)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </section>

              <section className="lblx-panel">
                <div className="lblx-panel-title">Purchase / GRN</div>
                <div className="lblx-panel-body lblx-panel-scroll">
                  <table className="lblx-intel-table">
                    <thead><tr><th className="lblx-num">Stock</th><th className="lblx-num">Free</th><th className="lblx-num">Dis%</th><th className="lblx-num">PTR</th><th className="lblx-num">MRP</th><th>GRN Date</th><th>Supplier</th></tr></thead>
                    <tbody>
                      {purchaseRows.map((row, i) => (
                        <tr key={i}>
                          <td className="lblx-num">{fmtQty(row.stock)}</td>
                          <td className="lblx-num">{fmtQty(row.free_qty)}</td>
                          <td className="lblx-num">{fmtPct(row.discount_pct)}</td>
                          <td className="lblx-num">{fmtMoney(row.ptr)}</td>
                          <td className="lblx-num">{fmtMoney(row.mrp)}</td>
                          <td>{fmtDate(row.grn_date)}</td>
                          <td>{row.supplier_name?.trim() || '—'}</td>
                        </tr>
                      ))}
                      {!purchaseRows.length && <tr><td colSpan={7} className="lblx-empty-mini">{intelLoading ? 'Loading…' : 'No purchase history.'}</td></tr>}
                    </tbody>
                  </table>
                </div>
              </section>

              <section className="lblx-panel">
                <div className="lblx-panel-title">Bill / Sales</div>
                <div className="lblx-panel-body lblx-panel-scroll">
                  <table className="lblx-intel-table">
                    <thead><tr><th className="lblx-num">Qty</th><th>Bill Time</th><th>Salesman</th><th>Customer</th><th className="lblx-num">Dis%</th><th className="lblx-num">MRP</th></tr></thead>
                    <tbody>
                      {saleRows.map((row, i) => (
                        <tr key={i}>
                          <td className="lblx-num">{fmtQty(row.qty)}</td>
                          <td>{fmtDate(row.bill_time)}</td>
                          <td title={row.salesman}>{row.salesman || '—'}</td>
                          <td title={row.customer}>{row.customer?.trim() || '—'}</td>
                          <td className="lblx-num">{fmtPct(row.discount_pct)}</td>
                          <td className="lblx-num">{fmtMoney(row.mrp)}</td>
                        </tr>
                      ))}
                      {!saleRows.length && <tr><td colSpan={6} className="lblx-empty-mini">{intelLoading ? 'Loading…' : 'No sales history.'}</td></tr>}
                    </tbody>
                  </table>
                </div>
              </section>
            </>
          )}
        </aside>
      </div>

      {assignOpen && (
        <div className="lblx-modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget && !assignBusy) setAssignOpen(false); }}>
          <div className="lblx-drawer" role="dialog" aria-modal="true" aria-label="Assign locations">
            <div className="lblx-modal-head">
              <strong>Location Assignment</strong>
              <button type="button" className="lblx-modal-x" onClick={() => setAssignOpen(false)}>✕</button>
            </div>
            <div className="lblx-modal-body">
              <div className="lblx-assign-summary">
                <b>{assignTargets.length}</b> product{assignTargets.length === 1 ? '' : 's'}
                <span> · </span>
                <b>{assignLetters.length}</b> letter{assignLetters.length === 1 ? '' : 's'}
                <span className="lblx-muted"> {selectedCodes.size ? 'from your selection' : 'all Y in this load'}</span>
              </div>
              <div className="lblx-assign-unitrow">
                <label>
                  <span>Unit</span>
                  <input value={assignForm.unit} onChange={(e) => { setAssignForm((f) => ({ ...f, unit: e.target.value.toUpperCase() })); setAssignPreview(null); }} placeholder="TAB / SYP" />
                </label>
                {!assignUnitIsSyp && assignLetters.length > 1 && (
                  <div className="lblx-setall">
                    <span>Set all</span>
                    <button type="button" className="ntm-button" onClick={() => setAllLetterModes('continue')}>Continue</button>
                    <button type="button" className="ntm-button" onClick={() => setAllLetterModes('new_label')}>New 1</button>
                    <button type="button" className="ntm-button" onClick={() => setAllLetterModes('single')}>Single</button>
                  </div>
                )}
              </div>
              {assignUnitIsSyp ? (
                <div className="lblx-note">SYP products bucket automatically by first letter — no per-letter box numbering.</div>
              ) : assignLetters.length ? (
                <div className="lblx-letter-list">
                  {assignLetters.map((L) => {
                    const m = assignForm.letterModes[L] || { mode: 'continue', startNumber: 1 };
                    return (
                      <div key={L} className="lblx-letter-row">
                        <span className="lblx-letter-chip">{L}</span>
                        <span className="lblx-letter-count">{assignLetterCounts[L]} item{assignLetterCounts[L] === 1 ? '' : 's'}</span>
                        <select value={m.mode} onChange={(e) => setLetterMode(L, { mode: e.target.value })}>
                          <option value="continue">Continue — fill last box</option>
                          <option value="new_label">New from 1</option>
                          <option value="single">Single product box</option>
                        </select>
                        {m.mode === 'new_label' ? (
                          <label className="lblx-letter-start"><span>#</span><input type="number" min={1} value={m.startNumber} onChange={(e) => setLetterMode(L, { startNumber: e.target.value })} /></label>
                        ) : <span />}
                      </div>
                    );
                  })}
                </div>
              ) : <div className="lblx-note">No letter-based products to box — names must start with a letter.</div>}
              {assignError && <div className="lblx-error">{assignError}</div>}
              {assignPreview && (
                <div className="lblx-preview">
                  <div className="lblx-preview-head">Preview · {assignPreview.assigned_count} product(s) → {assignPreview.boxes.length} box(es)</div>
                  {assignPreview.boxes.map((b) => (
                    <div key={b.box} className="lblx-preview-box">
                      <span>{b.box}</span>
                      <span>{b.existing > 0 ? `${b.existing}+${b.added}=${b.total}` : `${b.added} new`}{b.capacity ? ` / ${b.capacity}` : ''}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className="lblx-modal-foot">
              <button type="button" className="ntm-button" disabled={assignBusy} onClick={runPreview}>{assignBusy && !assignPreview ? 'Previewing…' : 'Preview'}</button>
              <button type="button" className="ntm-button ntm-button--primary" disabled={assignBusy || !assignPreview} onClick={runCommit}>{assignBusy && assignPreview ? 'Assigning…' : 'Assign'}</button>
            </div>
          </div>
        </div>
      )}

      {unitReplace && (
        <div className="lblx-modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget && !bulkBusy) setUnitReplace(null); }}>
          <div className="lblx-modal" role="dialog" aria-modal="true" aria-label="Replace unit">
            <div className="lblx-modal-head">
              <strong>Replace Unit</strong>
              <button type="button" className="lblx-modal-x" onClick={() => setUnitReplace(null)}>✕</button>
            </div>
            <div className="lblx-modal-body">
              <div className="lblx-replace-fields">
                <label><span>Find unit</span><input value={unitReplace.from} autoFocus onChange={(e) => setUnitReplace((u) => ({ ...u, from: e.target.value.toUpperCase() }))} placeholder="RM" /></label>
                <span className="lblx-arrow">→</span>
                <label><span>Replace with</span><input value={unitReplace.to} onChange={(e) => setUnitReplace((u) => ({ ...u, to: e.target.value.toUpperCase() }))} onKeyDown={(e) => { if (e.key === 'Enter' && unitReplaceMatches.length && !bulkBusy) applyUnitReplace(); }} placeholder="TAB" /></label>
              </div>
              <div className="lblx-note"><b>{unitReplaceMatches.length}</b> of {rows.length} loaded product(s) will change{unitReplace.to ? <> to <b>{unitReplace.to.trim().toUpperCase()}</b></> : ''}.</div>
            </div>
            <div className="lblx-modal-foot">
              <button type="button" className="ntm-button" disabled={bulkBusy} onClick={() => setUnitReplace(null)}>Cancel</button>
              <button type="button" className="ntm-button ntm-button--primary" disabled={bulkBusy || !unitReplaceMatches.length || !(unitReplace.to || '').trim()} onClick={applyUnitReplace}>
                {bulkBusy ? 'Replacing…' : `Replace${unitReplaceMatches.length ? ` (${unitReplaceMatches.length})` : ''}`}
              </button>
            </div>
          </div>
        </div>
      )}

      {finalise && (
        <div className="lblx-modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget && !finalise.busy) setFinalise(null); }}>
          <div className="lblx-modal lblx-modal-lg" role="dialog" aria-modal="true" aria-label="Finalise letter">
            <div className="lblx-modal-head">
              <strong>Finalise letter {activeLetter}</strong>
              <button type="button" className="lblx-modal-x" disabled={finalise.busy} onClick={() => setFinalise(null)}>✕</button>
            </div>
            <div className="lblx-modal-body">
              {finalise.loading && <div className="lblx-note">Checking letter {activeLetter}…</div>}
              {finalise.error && <div className="lblx-error">{finalise.error}</div>}
              {finalise.report && (
                <div className="lblx-finalise-report">
                  <b>✓ Letter {finalise.report.letter} finalised and locked.</b>
                  <span>{finalise.report.counts.total} products · <b className="is-y">{finalise.report.counts.included}</b> Y · <b className="is-n">{finalise.report.counts.excluded}</b> N</span>
                  <span>{finalise.report.auto_marked_n} unreviewed product(s) auto-marked N.</span>
                </div>
              )}
              {finalise.data && !finalise.report && (() => {
                const { counts, needs_review: needs } = finalise.data;
                const autoN = counts.unreviewed - counts.needs_review;
                return (
                  <>
                    <div className="lblx-finalise-counts">
                      <span><b>{counts.total}</b> products</span>
                      <span><b className="is-y">{counts.included}</b> Y</span>
                      <span><b className="is-n">{counts.excluded}</b> N</span>
                      <span><b>{counts.unreviewed}</b> unreviewed</span>
                      <span className={needs.length ? 'is-warn' : 'is-ok'}><b>{needs.length}</b> need review</span>
                    </div>
                    {needs.length > 0 ? (
                      <>
                        <div className="lblx-note">These products have stock &gt; 0 and sale unit &gt; 1 and are not reviewed yet.</div>
                        <table className="lblx-intel-table">
                          <thead><tr><th>Code</th><th>Product</th><th>Unit</th><th className="lblx-num">Sale U</th><th className="lblx-num">Stock</th><th>Old Loc</th><th /></tr></thead>
                          <tbody>
                            {needs.map((row) => (
                              <tr key={row.product_code}>
                                <td>{row.product_code}</td>
                                <td>{row.product_name}</td>
                                <td>{row.unit_description || '—'}</td>
                                <td className="lblx-num">{fmtQty(row.sale_unit)}</td>
                                <td className="lblx-num">{fmtQty(row.total_stock)}</td>
                                <td>{row.current_sublocation || '—'}</td>
                                <td>
                                  <button type="button" className="lblx-review-badge is-yes" disabled={finalise.busy} onClick={() => reviewFinaliseRows([row.product_code], 'Y')}>Y</button>
                                  <button type="button" className="lblx-review-badge is-no" disabled={finalise.busy} onClick={() => reviewFinaliseRows([row.product_code], 'N')}>N</button>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </>
                    ) : <div className="lblx-note is-ok">Every product that needs a label decision is reviewed.</div>}
                    {autoN > 0 && <div className="lblx-note">On Finalise, {autoN} other unreviewed product(s) are auto-marked N.</div>}
                    {!admin && <div className="lblx-note">Only a super admin can finalise and lock a letter.</div>}
                  </>
                );
              })()}
            </div>
            <div className="lblx-modal-foot">
              {finalise.data && !finalise.report && finalise.data.needs_review.length > 0 && (
                <button type="button" className="ntm-button" disabled={finalise.busy || isLocked} onClick={() => reviewFinaliseRows(finalise.data.needs_review.map((r) => r.product_code), 'Y')}>
                  Mark all {finalise.data.needs_review.length} Y
                </button>
              )}
              <button type="button" className="ntm-button" disabled={finalise.busy} onClick={() => setFinalise(null)}>{finalise.report ? 'Close' : 'Cancel'}</button>
              {admin && finalise.data && !finalise.report && (
                <button type="button" className="ntm-button ntm-button--primary" disabled={finalise.busy || finalise.data.needs_review.length > 0} onClick={runFinalise}>
                  {finalise.busy ? 'Working…' : `Finalise & Lock ${activeLetter}`}
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {queueOpen && (
        <div className="lblx-modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) setQueueOpen(false); }}>
          <div className="lblx-modal lblx-modal-lg" role="dialog" aria-modal="true" aria-label="Label queue">
            <div className="lblx-modal-head">
              <strong>Label Queue{filteredQueueRows.length ? ` — ${filteredQueueRows.length}` : ''}</strong>
              <div className="lblx-queue-actions">
                <label className="lblx-field">
                  <span>Show</span>
                  <select value={queuePrintFilter} onChange={(e) => setQueuePrintFilter(e.target.value)}>
                    <option value="all">All</option>
                    <option value="ready">Ready to print</option>
                    <option value="printed">Already printed</option>
                  </select>
                </label>
                <label className="lblx-field">
                  <span>Letter</span>
                  <MultiPicker options={queueLetters} selected={queueLetterSel} onChange={setQueueLetterSel} placeholder="All letters" noun="letter" />
                </label>
                {admin && (
                  <button type="button" className="ntm-button" disabled={!filteredQueueRows.some((r) => r.label_created_at) || queueClearBusy} onClick={clearPrintedInView}>
                    {queueClearBusy ? 'Clearing…' : 'Clear Printed'}
                  </button>
                )}
                <button type="button" className="ntm-button ntm-button--primary" disabled={!filteredQueueRows.length} onClick={printQueue}>Print / Export</button>
                <button type="button" className="ntm-button" disabled={!filteredQueueRows.length || pdfBusy} onClick={exportQueuePdf} title="Box-wise A3 PDF">{pdfBusy ? 'Building PDF…' : 'Export PDF (A3)'}</button>
                <button type="button" className="lblx-modal-x" onClick={() => setQueueOpen(false)}>✕</button>
              </div>
            </div>
            <div className="lblx-modal-body">
              {queueBusy ? <div className="lblx-empty-mini">Loading queue…</div> : !queueRows.length ? (
                <div className="lblx-empty-mini">No products assigned yet. Assign locations to build the queue.</div>
              ) : !filteredQueueRows.length ? (
                <div className="lblx-empty-mini">No labels match this filter.</div>
              ) : (
                <table className="lblx-intel-table">
                  <thead><tr><th>Location</th><th>Product</th><th>Unit</th><th className="lblx-num">MRP</th><th>Assigned</th><th>Printed</th></tr></thead>
                  <tbody>
                    {filteredQueueRows.map((r) => (
                      <tr key={r.product_code}>
                        <td><b>{r.location}</b></td>
                        <td title={r.product_name}>{r.product_name}</td>
                        <td>{r.unit_description || '-'}</td>
                        <td className="lblx-num">{fmtMoney(r.mrp)}</td>
                        <td>{fmtDate(r.assigned_at)}</td>
                        <td>{r.label_created_at ? '✓' : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      )}

      {confirm && (
        <div className="lblx-modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget && !bulkBusy) setConfirm(null); }}>
          <div className="lblx-modal lblx-confirm" role="dialog" aria-modal="true" aria-label={confirm.title}>
            <div className="lblx-modal-head"><strong>{confirm.title}</strong></div>
            <div className="lblx-modal-body">{confirm.body.map((line, i) => <p key={i}>{line}</p>)}</div>
            <div className="lblx-modal-foot">
              <button type="button" className="ntm-button" disabled={bulkBusy} onClick={() => setConfirm(null)}>Cancel</button>
              <button type="button" className="ntm-button lblx-danger" disabled={bulkBusy} onClick={confirm.onConfirm}>{bulkBusy ? 'Working…' : confirm.confirmLabel}</button>
            </div>
          </div>
        </div>
      )}

      {toast && <div className={`lblx-toast lblx-toast-${toast.kind}`} role="status">{toast.text}</div>}
    </PageLayout>
  );
}
