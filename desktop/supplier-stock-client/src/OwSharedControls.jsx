import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { OW_PANEL_DEFS } from './orderWorkspaceView.js';

// Grid/export building blocks shared across Order Workspace, Procurement
// (via App.jsx's PROCUREMENT_UI bridge, so ProcurementWorkspace.jsx never
// imports App.jsx) and the Label Exporter screen. Extracted from App.jsx
// unchanged (NEXORA MEDIQ Phase 4 structural refactor, see
// docs/NEXORA_MEDIQ_AUDIT/17_ORDER_WORKSPACE_EXTRACTION_MAP.md) -- no
// behavior was altered in the move.

export const OW_GEAR_PATH = 'M19.4 13a7.8 7.8 0 0 0 .1-1 7.8 7.8 0 0 0-.1-1l2-1.6-2-3.4-2.4 1a8 8 0 0 0-1.7-1L15 3.5h-4L10.7 6A8 8 0 0 0 9 7L6.6 6l-2 3.4 2 1.6a7.8 7.8 0 0 0-.1 1 7.8 7.8 0 0 0 .1 1l-2 1.6 2 3.4L9 17a8 8 0 0 0 1.7 1l.3 2.5h4l.3-2.5a8 8 0 0 0 1.7-1l2.4 1 2-3.4-2-1.6ZM12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7Zm0 2a1.5 1.5 0 1 1 0 3 1.5 1.5 0 0 1 0-3Z';

// The single canonical set of desktop export column keys for Order
// Workspace / Procurement exports. Mirrored server-side in
// backend/modules/procurement/pm_schemas.py's _VALID_EXPORT_COLUMNS --
// keep both in sync if a column is added/renamed here.
export const OW_EXPORT_COLUMN_DEFS = [
  { key: 'productCode', label: 'Product Code', required: true },
  { key: 'productName', label: 'Product Name', required: true },
  { key: 'orderQty', label: 'Order Qty', required: true },
  { key: 'saleUnit', label: 'Sale Unit', required: false },
  { key: 'mrp', label: 'MRP', required: false },
  { key: 'discount', label: 'Discount', required: false },
  { key: 'category', label: 'Category', required: false },
  { key: 'subLocation', label: 'Sub Location', required: false },
  { key: 'rack', label: 'Rack', required: false },
  { key: 'supplierProductCode', label: 'Supplier Code', required: false },
  { key: 'supplierProductName', label: 'Supplier Name', required: false }
];

// Ordered list of column keys for a grid (saved order first, then any new base
// columns appended so a config from an older build never drops a column).
export function orderOwKeys(base, cfg) {
  const keys = base.map((c) => c.key);
  const saved = (cfg?.order || []).filter((k) => keys.includes(k));
  keys.forEach((k) => { if (!saved.includes(k)) saved.push(k); });
  return saved;
}

// Heal a saved column config written by a build that predates a column: if an
// explicit order was persisted but is missing a base column, splice that column
// in right after its default left-neighbour instead of letting orderOwKeys
// append it to the far right (where users read a mid-grid column as "gone").
// Currently rescues 'saleUnit', added to the Label grid after some sessions were
// already saved. Width/hidden state is untouched.
export function healColOrder(base, cfg, rescueKeys) {
  if (!cfg || !Array.isArray(cfg.order) || !cfg.order.length) return cfg;
  const order = [...cfg.order];
  let changed = false;
  for (const key of rescueKeys) {
    if (order.includes(key)) continue;
    const basePos = base.findIndex((c) => c.key === key);
    if (basePos < 0) continue;
    let insertAt = order.length;
    for (let i = basePos - 1; i >= 0; i--) {
      const idx = order.indexOf(base[i].key);
      if (idx >= 0) { insertAt = idx + 1; break; }
    }
    order.splice(insertAt, 0, key);
    changed = true;
  }
  return changed ? { ...cfg, order } : cfg;
}

// Visible, ordered columns with any user width override applied.
export function resolveOwColumns(base, cfg) {
  const byKey = new Map(base.map((c) => [c.key, c]));
  return orderOwKeys(base, cfg)
    .map((k) => byKey.get(k))
    .filter((c) => c && !(cfg?.hidden && cfg.hidden[c.key]))
    .map((c) => {
      const w = cfg?.widths ? cfg.widths[c.key] : undefined;
      return { ...c, width: (w != null && w !== '') ? Number(w) : c.width };
    });
}

// Modern grid-settings card (reuses the app's .grid-settings-panel styling):
// show/hide, reorder and resize the columns of ONE grid.
// Order Workspace layout (owner request 2026-10-24): every role -- PM
// included -- can size the grid rows and move/size the detail panels. Saved
// per PC (localStorage), same as the column settings.
// The four detail panels can each be shown/hidden, docked in the side column
// or the strip under the grid, and reordered.
const OW_LAYOUT_OPTIONS = [
  { key: 'rowSize', label: 'Row height', options: [['compact', 'Compact'], ['normal', 'Normal'], ['large', 'Large']] },
  { key: 'rowWeight', label: 'Row font', options: [['normal', 'Normal'], ['bold', 'Bold']] },
  { key: 'sideWidth', label: 'Side panel width', options: [['narrow', 'Narrow'], ['normal', 'Normal'], ['wide', 'Wide']] },
  { key: 'bottomHeight', label: 'Bottom panel height', options: [['small', 'Small'], ['normal', 'Normal'], ['large', 'Large']] },
  { key: 'qtyCheckStyle', label: 'Qty check', options: [['tick', 'Tick'], ['text', 'Text']] },
];
export function OwGridSettings({ title, anchorRef, base, cfg, onToggle, onMove, onWidth, onReset, onClose, layout, onLayout }) {
  const setPanel = (key, patch) => onLayout({ panels: layout.panels.map((p) => (p.key === key ? { ...p, ...patch } : p)) });
  const movePanel = (idx, dir) => {
    const n = [...layout.panels]; const j = idx + dir;
    if (j < 0 || j >= n.length) return;
    [n[idx], n[j]] = [n[j], n[idx]];
    onLayout({ panels: n });
  };
  const ref = useRef(null);
  const [pos, setPos] = useState(null);
  // Wide two-pane card (columns | layout) sized to fit the viewport without
  // scrolling; centred on the gear button and clamped inside the window.
  useLayoutEffect(() => {
    const a = anchorRef.current;
    if (!a) return;
    const r = a.getBoundingClientRect();
    const vw = window.innerWidth;
    const width = Math.min(onLayout ? 1000 : 620, vw - 32);
    const left = Math.min(Math.max(16, r.left + r.width / 2 - width / 2), vw - width - 16);
    setPos({ top: r.bottom + 8, left, width });
  }, [anchorRef, onLayout]);
  useEffect(() => {
    function onDoc(e) { if (ref.current && !ref.current.contains(e.target) && !anchorRef.current?.contains(e.target)) onClose(); }
    function onEsc(e) { if (e.key === 'Escape') onClose(); }
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onEsc);
    return () => { document.removeEventListener('mousedown', onDoc); document.removeEventListener('keydown', onEsc); };
  }, [onClose, anchorRef]);
  if (!pos) return null;
  const byKey = new Map(base.map((c) => [c.key, c]));
  const orderKeys = orderOwKeys(base, cfg).filter((key) => byKey.has(key));
  const shown = orderKeys.filter((key) => !(cfg?.hidden && cfg.hidden[key])).length;
  const seg = (options, isOn, onPick, disabled) => (
    <div className="ow-settings__seg" role="group">
      {options.map(([value, label]) => (
        <button key={value} type="button" className={`ow-settings__seg-btn${isOn(value) ? ' is-on' : ''}`}
          disabled={disabled} onClick={() => onPick(value)}>{label}</button>
      ))}
    </div>
  );
  return createPortal(
    <div className={`grid-settings-panel ow-settings${onLayout ? '' : ' ow-settings--cols-only'}`} ref={ref} role="dialog"
      aria-label={`${title} grid settings`}
      style={{ position: 'fixed', top: pos.top, left: pos.left, width: pos.width, maxHeight: `calc(100vh - ${pos.top + 12}px)` }}>
      <header className="ow-settings__head">
        <div className="ow-settings__heading">
          <strong>{title}</strong>
          <span>Grid settings · columns{onLayout ? ' & layout' : ''}</span>
        </div>
        <button type="button" className="ow-settings__reset" onClick={onReset}
          title={onLayout ? 'Reset this grid\'s columns and the whole layout' : 'Reset columns'}>↺ Reset to default</button>
        <button type="button" className="ow-settings__close" onClick={onClose} aria-label="Close settings" title="Close (Esc)">✕</button>
      </header>
      <div className="ow-settings__body">
        <section className="ow-settings__pane">
          <div className="ow-settings__pane-head">
            <span className="ow-settings__pane-title">Columns</span>
            <span className="ow-settings__pane-hint">{shown} of {orderKeys.length} shown · width px, blank = default</span>
          </div>
          <ul className="ow-settings__cols">
            {orderKeys.map((key, idx, arr) => {
              const col = byKey.get(key);
              const visible = !(cfg?.hidden && cfg.hidden[key]);
              const width = cfg?.widths ? cfg.widths[key] : undefined;
              return (
                <li className={`ow-settings__col${visible ? '' : ' is-off'}${col.locked ? ' is-locked' : ''}`} key={key}>
                  <label className="ow-settings__col-name" title={col.locked ? `${col.label} (always visible)` : col.label}>
                    <input type="checkbox" checked={visible} disabled={col.locked} onChange={() => onToggle(key)} />
                    <span>{col.label}</span>
                    {col.locked && <i className="ow-settings__lock" aria-hidden="true">🔒</i>}
                  </label>
                  <span className="ow-settings__move">
                    <button type="button" disabled={idx === 0} title="Move up" onClick={() => onMove(key, -1)}>▲</button>
                    <button type="button" disabled={idx === arr.length - 1} title="Move down" onClick={() => onMove(key, 1)}>▼</button>
                  </span>
                  <input className="ow-settings__width" type="number" min="30" max="400" step="2" value={width ?? ''}
                    placeholder={String(col.width)} onChange={(e) => onWidth(key, e.target.value)}
                    title="Width in px (blank = default)" aria-label={`${col.label} column width`} />
                </li>
              );
            })}
          </ul>
        </section>
        {onLayout && (
          <section className="ow-settings__pane ow-settings__pane--layout">
            <div className="ow-settings__pane-head"><span className="ow-settings__pane-title">Layout</span></div>
            <div className="ow-settings__opts">
              <div className="ow-settings__opt">
                <span>Side panel</span>
                {seg([['right', 'Right'], ['left', 'Left'], ['hidden', 'Hidden']],
                  (v) => (v === 'hidden' ? layout.sideHidden : !layout.sideHidden && layout.sidePosition === v),
                  (v) => onLayout(v === 'hidden' ? { sideHidden: true } : { sidePosition: v, sideHidden: false }))}
              </div>
              {OW_LAYOUT_OPTIONS.map((group) => (
                <div className="ow-settings__opt" key={group.key}>
                  <span>{group.label}</span>
                  {seg(group.options, (v) => layout[group.key] === v, (v) => onLayout({ [group.key]: v }),
                    group.key === 'sideWidth' && layout.sideHidden)}
                </div>
              ))}
            </div>
            <div className="ow-settings__pane-head"><span className="ow-settings__pane-title">Detail panels</span>
              <span className="ow-settings__pane-hint">show, dock &amp; order</span></div>
            <ul className="ow-settings__panels">
              {layout.panels.map((p, idx, arr) => {
                const def = OW_PANEL_DEFS.find((d) => d.key === p.key);
                return (
                  <li className={`ow-settings__col${p.hidden ? ' is-off' : ''}`} key={p.key}>
                    <label className="ow-settings__col-name" title={def?.label}>
                      <input type="checkbox" checked={!p.hidden} onChange={() => setPanel(p.key, { hidden: !p.hidden })} />
                      <span>{def?.label}</span>
                    </label>
                    {seg([['side', 'Side'], ['bottom', 'Bottom']], (v) => p.dock === v, (v) => setPanel(p.key, { dock: v }))}
                    <span className="ow-settings__move">
                      <button type="button" disabled={idx === 0} title="Move up" onClick={() => movePanel(idx, -1)}>▲</button>
                      <button type="button" disabled={idx === arr.length - 1} title="Move down" onClick={() => movePanel(idx, 1)}>▼</button>
                    </span>
                  </li>
                );
              })}
            </ul>
          </section>
        )}
      </div>
    </div>,
    document.body
  );
}

// Supplier picker, following VB.NET's txtSupplierSearch + dgvSupplierList
// pair exactly (Form1.vb txtSupplierSearch_TextChanged / _KeyDown,
// dgvSupplierList_KeyDown / _KeyPress): typing re-queries and opens the list;
// Down moves focus into the list (or selects the next row once inside it);
// Enter on a highlighted row commits it -- fills the box with the supplier
// name, hides the list, clears the search text -- exactly like VB.NET's
// dgvSupplierList_KeyPress committing and then setting Visible = False;
// Escape hides the list and clears the box, same as VB.NET. There is no
// mouse-click selection: the real VB.NET form's dgvSupplierList click
// handlers (_CellClick, _CellContentClick) never set the supplier, so this
// matches a keyboard-only picker instead of inventing click-to-pick behavior
// that can race with the hide-on-select sequence below.
export function OwSupplierPicker({ suppliers, value, onChange }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const wrapRef = useRef(null);
  const inputRef = useRef(null);
  const listRef = useRef(null);

  useEffect(() => {
    function onDoc(e) { if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false); }
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  // Name OR code, substring, case-insensitive on BOTH sides -- supplier codes
  // are alphanumeric (e.g. NMV's backfilled UnifiedSupplierCode), so matching a
  // lowercased search term against an un-lowercased code never hit, which is
  // why "search by code" turned up nothing. Cap the rendered rows (hundreds of
  // suppliers per store) and keep the code visible so a code search is useful.
  const term = query.trim().toLowerCase();
  // Require 2+ characters before showing any matches -- on focus/click the
  // box opens with an empty query, and dumping the full few-hundred-row
  // supplier list on screen before the user has typed anything to narrow it
  // is just noise to scroll past.
  const filtered = useMemo(() => {
    if (term.length < 2) return [];
    const list = suppliers.filter((s) =>
      String(s.supplier_name || '').toLowerCase().includes(term)
      || String(s.supplier_code || '').toLowerCase().includes(term));
    return list.slice(0, 50);
  }, [suppliers, term]);

  // Reset the keyboard-active row whenever the result set or open-state changes.
  useEffect(() => { setActive(0); }, [term, open]);

  // Commits the row -- fills the box, hides the list, clears the search term.
  // Deliberately does NOT refocus the input (matches dgvSupplierList_KeyPress,
  // which leaves focus wherever the committing keypress happened) and
  // deliberately does not touch `open` via any other effect afterward, so
  // nothing can re-open the list once this runs.
  const commit = (s) => { onChange(s); setQuery(''); setOpen(false); };

  const onInputKeyDown = (e) => {
    if (e.key === 'Escape') {
      e.preventDefault(); setOpen(false); setQuery('');
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (!filtered.length) return;
      setOpen(true);
      // Hand focus to the list, same as VB's txtSupplierSearch_KeyDown Down
      // case (dgvSupplierList.Focus()) -- from here the list's own KeyDown
      // handler drives further Up/Down/Enter.
      requestAnimationFrame(() => listRef.current?.focus());
      return;
    }
    if (e.key === 'Enter') {
      e.preventDefault();
      if (!filtered.length) return;
      // Typed an exact supplier CODE -- load that one directly, even if the
      // name search also turned up other matches (an exact code is
      // unambiguous on its own). Otherwise, Enter with exactly one name/code
      // match on screen commits that match directly too, without first
      // needing Down to move into the list -- Down+Enter still works exactly
      // as before for browsing multiple matches.
      const exactCode = filtered.find((s) => String(s.supplier_code || '').toLowerCase() === term);
      if (exactCode) { commit(exactCode); return; }
      if (filtered.length === 1) commit(filtered[0]);
    }
  };

  const onListKeyDown = (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((i) => Math.min(i + 1, filtered.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((i) => Math.max(i - 1, 0)); }
    else if (e.key === 'Enter') {
      e.preventDefault();
      const chosen = filtered[active];
      if (chosen) commit(chosen);
    } else if (e.key === 'Escape') {
      e.preventDefault(); setOpen(false); setQuery(''); inputRef.current?.focus();
    }
  };

  return (
    <div className="ow-supplier-pick" ref={wrapRef}>
      <input
        ref={inputRef}
        className="ow-supplier-input"
        type="text"
        placeholder="Search supplier or code…"
        value={open ? query : (value?.supplier_name || '')}
        onFocus={(e) => { setOpen(true); setQuery(''); e.target.select(); }}
        onClick={(e) => { if (!open) { setOpen(true); setQuery(''); } e.target.select(); }}
        onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
        onKeyDown={onInputKeyDown}
        aria-label="Search and select supplier"
        role="combobox" aria-expanded={open} autoComplete="off"
      />
      {value && !open && (
        <>
          <button type="button" className="ow-supplier-switch" title="Switch supplier" aria-label="Switch supplier"
            onMouseDown={(e) => { e.preventDefault(); setOpen(true); setQuery(''); requestAnimationFrame(() => inputRef.current?.focus()); }}>▼</button>
          <button type="button" className="ow-supplier-clear" title="Clear supplier" aria-label="Clear supplier" onClick={() => onChange(null)}>×</button>
        </>
      )}
      {open && (
        // tabIndex so Down from the input can Focus() this list, matching
        // dgvSupplierList.Focus() in VB.NET; onBlur hides it, matching the
        // list's visibility being tied to active use, not a separate toggle.
        <ul ref={listRef} className="ow-supplier-list" role="listbox" tabIndex={-1}
          onKeyDown={onListKeyDown} onBlur={(e) => { if (!wrapRef.current?.contains(e.relatedTarget)) setOpen(false); }}>
          {/* UnifiedSupplierCode can repeat / be blank, so the index keeps keys
              unique for this display-only list. Click commits the row (mouse
              users expect this even though VB.NET's grid was keyboard-only);
              use onMouseDown so it fires before the input's blur/onBlur-driven
              close logic hides the list. */}
          {filtered.map((s, i) => (
            <li key={`${s.supplier_code}-${i}`} role="option" aria-selected={i === active}
              className={i === active ? 'is-active' : (value?.supplier_code === s.supplier_code ? 'is-selected' : undefined)}
              onMouseEnter={() => setActive(i)}
              onMouseDown={(e) => { e.preventDefault(); commit(s); }}>
              <span className="ow-supplier-name">{s.supplier_name}</span>
              <span className="ow-supplier-code">{s.supplier_code}</span>
            </li>
          ))}
          {!filtered.length && (
            <li className="ow-supplier-empty">
              {term.length < 2 ? 'Type at least 2 characters…' : 'No suppliers match.'}
            </li>
          )}
        </ul>
      )}
    </div>
  );
}

// Export options popover: split-count + scope, anchored to the Export button.
export function OwExportCard({
  anchorRef, splitCount, setSplitCount, exporting, scopeLabel, onExport, onClose,
  exportSettings, onUpdateExportSettings,
  // Pending has no supplier to assign to and no per-column customization (its
  // export always carries the grid's own fixed column set) -- these two
  // props let the same card serve both without forking it. Defaults
  // preserve the existing By Supplier/Assigned behavior exactly.
  headline = 'Assigns every ordered row to this supplier, then downloads',
  showColumns = true, showSupplierWise = true,
  // Procurement-only (never passed by OW): when a super admin has set tenant
  // export defaults and the signed-in role isn't a super admin, file type and
  // columns are locked to those defaults -- "rows per file" stays editable.
  locked = false, lockedHint = null,
}) {
  const ref = useRef(null);
  useEffect(() => {
    function onDoc(e) { if (ref.current && !ref.current.contains(e.target) && !anchorRef.current?.contains(e.target)) onClose(); }
    function onEsc(e) { if (e.key === 'Escape') onClose(); }
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onEsc);
    return () => { document.removeEventListener('mousedown', onDoc); document.removeEventListener('keydown', onEsc); };
  }, [onClose, anchorRef]);
  // Centred in the window rather than anchored under the Export button: the
  // button can wrap to the toolbar's left edge on narrower windows, and a
  // right-anchored card then ran off-screen to the left.
  return createPortal(
    <div className="grid-settings-panel ow-export-card ow-export-card--centered" ref={ref} role="dialog" aria-label="Export options">
      <div className="grid-settings-panel__head">
        <strong>Export to Excel</strong>
        <span>{headline}</span>
      </div>
      <div className="grid-settings-panel__body ow-export-body">
        <div className="ow-export-scope">Scope: <b>{scopeLabel}</b></div>

        <div className="ow-export-field ow-export-path">
          <span>Save to</span>
          <code className="ow-export-path-val" title={exportSettings.basePath}>{exportSettings.basePath}\ddmmyyyy\order no\</code>
          <button
            type="button"
            className="ow-btn ow-btn-sm"
            disabled={!window.nexoraDesktop?.chooseExportFolder}
            title={window.nexoraDesktop?.chooseExportFolder ? 'Choose a different default export folder' : 'Only available in the desktop app'}
            onClick={async () => {
              const picked = await window.nexoraDesktop.chooseExportFolder(exportSettings.basePath);
              if (picked) onUpdateExportSettings({ basePath: picked });
            }}
          >
            Change…
          </button>
        </div>

        <label className="ow-export-field">
          <span>File type</span>
          <select
            value={exportSettings.fileFormat}
            disabled={locked}
            onChange={(e) => onUpdateExportSettings({ fileFormat: e.target.value })}
            aria-label="Export file format"
          >
            <option value="xls">Excel 97-2003 (.xls)</option>
            <option value="xlsx">Excel (.xlsx)</option>
            <option value="csv">CSV (.csv)</option>
          </select>
        </label>

        <label className="ow-export-field">
          <span>Rows per file</span>
          <input
            type="number" min="0" step="1" value={splitCount || ''} placeholder="0 = single file"
            onChange={(e) => setSplitCount(Math.max(0, Number(e.target.value) || 0))}
            aria-label="Rows per file (0 for a single file)"
          />
        </label>

        <label className="ow-export-check">
          <input
            type="checkbox"
            checked={!!exportSettings.images}
            onChange={(e) => onUpdateExportSettings({ images: e.target.checked })}
          />
          <span>Also save as images (20 products per image)</span>
        </label>

        {showSupplierWise && (
          <label className="ow-export-check">
            <input
              type="checkbox"
              checked={exportSettings.supplierWise}
              onChange={(e) => onUpdateExportSettings({ supplierWise: e.target.checked })}
            />
            <span>Separate subfolder per supplier</span>
          </label>
        )}

        {showColumns && (
          <div className="ow-export-columns">
            <span className="ow-export-columns-label">Columns</span>
            <div className="ow-export-columns-grid">
              {OW_EXPORT_COLUMN_DEFS.map((col) => (
                <label key={col.key} className="ow-export-check ow-export-col-check">
                  <input
                    type="checkbox"
                    checked={col.required || exportSettings.columns[col.key]}
                    disabled={col.required || locked}
                    onChange={(e) => onUpdateExportSettings({ columns: { ...exportSettings.columns, [col.key]: e.target.checked } })}
                  />
                  <span>{col.label}{col.required && ' *'}</span>
                </label>
              ))}
            </div>
            {locked && lockedHint && <p className="ow-export-hint">{lockedHint}</p>}
            <p className="ow-export-hint">* Product Code, Product Name and Order Qty are always included.</p>
          </div>
        )}

        <button type="button" className="ow-btn ow-btn-primary ow-export-go" disabled={exporting} onClick={onExport}>{exporting ? 'Exporting…' : '⬇ Export'}</button>
      </div>
    </div>,
    document.body
  );
}
