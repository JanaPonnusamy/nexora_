import { useState } from 'react'
import type { DocImportItem, DocImportRow, HeaderPatch, SupplierAssignRequest } from '../../types/documentExtraction'
import { headerHighlights, reconcileTotals } from './reviewChecks'

interface HeaderPanelProps {
  header: DocImportRow
  items: DocImportItem[]
  onSaveHeader: (patch: HeaderPatch) => void | Promise<void>
  onAssignSupplier: (body: SupplierAssignRequest) => void | Promise<void>
  saving?: boolean
}

interface FieldDef {
  key: keyof HeaderPatch
  label: string
  type: 'text' | 'date' | 'number'
}

const INVOICE_FIELDS: FieldDef[] = [
  { key: 'invoice_number', label: 'Invoice Number', type: 'text' },
  { key: 'invoice_date', label: 'Invoice Date', type: 'date' },
  { key: 'invoice_type', label: 'Invoice Type', type: 'text' },
  { key: 'order_number', label: 'Order Number', type: 'text' },
  { key: 'transport', label: 'Transport', type: 'text' },
  { key: 'salesman', label: 'Salesman', type: 'text' },
  { key: 'credit_days', label: 'Credit Days', type: 'number' },
  { key: 'irn_number', label: 'IRN Number', type: 'text' },
  { key: 'ack_number', label: 'Ack Number', type: 'text' },
  { key: 'ack_date', label: 'Ack Date', type: 'date' },
]

const MONEY_FIELDS: { key: keyof HeaderPatch; label: string }[] = [
  { key: 'gross_amount', label: 'Gross' },
  { key: 'discount_amount', label: 'Discount' },
  { key: 'scheme_discount', label: 'Scheme Disc.' },
  { key: 'cash_discount', label: 'Cash Disc.' },
  { key: 'taxable_amount', label: 'Taxable' },
  { key: 'cgst_amount', label: 'CGST' },
  { key: 'sgst_amount', label: 'SGST' },
  { key: 'igst_amount', label: 'IGST' },
  { key: 'cess_amount', label: 'CESS' },
  { key: 'round_off', label: 'Round Off' },
]

function toStr(v: unknown): string {
  return v == null ? '' : String(v)
}

/** Extracted header, redesigned around what a receiving-desk operator
 *  actually checks first: is the supplier right, does the invoice balance,
 *  and only then the rest of the metadata. Every field auto-saves on blur
 *  (no separate "Save Header" click) so correcting an OCR miss is a single
 *  tab-and-type instead of a modal round trip. */
export function HeaderPanel({ header, items, onSaveHeader, onAssignSupplier, saving }: HeaderPanelProps) {
  // is_supplier_unknown defaults to false at upload time and only becomes a
  // real signal once the supplier-detection engine has actually run — until
  // then (or if detection ran but found nothing) matched_supplier_code is
  // still null, so "confirmed" must require an actual code, not just the
  // absence of the unknown flag. Otherwise a brand-new, not-yet-processed
  // invoice shows a false green "confirmed" banner with no supplier name.
  const supplierNeedsAction = header.is_supplier_unknown || !header.matched_supplier_code

  const [supplierCode, setSupplierCode] = useState(header.matched_supplier_code ?? '')
  const [supplierName, setSupplierName] = useState(header.supplier_name ?? '')
  const [editingSupplier, setEditingSupplier] = useState(supplierNeedsAction)

  // Re-seed the local supplier form whenever the server's own header data
  // moves on (a different invoice, or a fresh value after save) — adjusted
  // during render rather than in an effect, matching the codebase's own
  // pattern for "reset local state when a prop changes" (see ProductGrid's
  // prevSelectedId comparison).
  const [prevHeaderKey, setPrevHeaderKey] = useState(
    `${header.import_id}:${header.matched_supplier_code}:${header.supplier_name}:${header.is_supplier_unknown}`,
  )
  const headerKey = `${header.import_id}:${header.matched_supplier_code}:${header.supplier_name}:${header.is_supplier_unknown}`
  if (headerKey !== prevHeaderKey) {
    setPrevHeaderKey(headerKey)
    setSupplierCode(header.matched_supplier_code ?? '')
    setSupplierName(header.supplier_name ?? '')
    setEditingSupplier(supplierNeedsAction)
  }

  const highlights = headerHighlights(header).filter((h) => h !== 'Unknown Supplier')
  const reconcile = reconcileTotals(header, items)

  function saveField(key: keyof HeaderPatch, type: FieldDef['type'], raw: string) {
    const current = toStr((header as unknown as Record<string, unknown>)[key])
    if (raw === current) return
    const value = raw === '' ? null : type === 'number' ? Number(raw) : raw
    void onSaveHeader({ [key]: value } as HeaderPatch)
  }

  return (
    <div className="dx-header">
      {/* ---- Supplier ---- */}
      {supplierNeedsAction ? (
        <div className="dx-supplier-callout dx-supplier-callout--unknown">
          <div className="dx-supplier-callout__title">
            <i className="bi bi-exclamation-octagon-fill" /> Unknown Supplier — action needed
          </div>
          <div className="dx-supplier-callout__row">
            <input
              className="form-control form-control-sm" placeholder="Supplier code"
              value={supplierCode} onChange={(e) => setSupplierCode(e.target.value)}
            />
            <input
              className="form-control form-control-sm" placeholder="Supplier name"
              value={supplierName} onChange={(e) => setSupplierName(e.target.value)}
            />
            <button
              type="button" className="btn btn-warning btn-sm text-nowrap" disabled={saving || !supplierCode}
              onClick={() => void onAssignSupplier({ matched_supplier_code: supplierCode, supplier_name: supplierName })}
            >
              Assign Supplier
            </button>
          </div>
        </div>
      ) : (
        <div className="dx-supplier-callout dx-supplier-callout--ok">
          <i className="bi bi-check-circle-fill" />
          {editingSupplier ? (
            <div className="dx-supplier-callout__row">
              <input className="form-control form-control-sm" value={supplierCode} onChange={(e) => setSupplierCode(e.target.value)} />
              <input className="form-control form-control-sm" value={supplierName} onChange={(e) => setSupplierName(e.target.value)} />
              <button
                type="button" className="btn btn-primary btn-sm" disabled={saving || !supplierCode}
                onClick={async () => { await onAssignSupplier({ matched_supplier_code: supplierCode, supplier_name: supplierName }); setEditingSupplier(false) }}
              >
                Save
              </button>
              <button type="button" className="btn btn-outline-secondary btn-sm" onClick={() => setEditingSupplier(false)}>Cancel</button>
            </div>
          ) : (
            <>
              <span className="dx-supplier-callout__name">{header.supplier_name}</span>
              <span className="text-muted small">{header.matched_supplier_code}</span>
              {isLowConfidenceMatch(header) && <span className="badge text-bg-warning">Low confidence match</span>}
              <button type="button" className="btn btn-link btn-sm ms-auto" onClick={() => setEditingSupplier(true)}>Change</button>
            </>
          )}
        </div>
      )}

      {/* ---- Financial Reconciliation ---- */}
      <h6 className="dx-section-title">Financial Reconciliation</h6>
      <div className="dx-reconcile">
        {reconcile.map((c) => (
          <div key={c.label} className={`dx-reconcile__badge${c.balanced ? '' : ' dx-reconcile__badge--off'}`} title={c.label}>
            <i className={`bi ${c.balanced ? 'bi-check-circle-fill' : 'bi-exclamation-triangle-fill'}`} />
            {c.balanced ? 'Balances' : `Off by ${fmt(Math.abs((c.extracted ?? 0) - c.computed))}`}
          </div>
        ))}
      </div>
      <div className="dx-tiles">
        {MONEY_FIELDS.map(({ key, label }) => (
          <MoneyTile key={key} label={label} value={toStr((header as unknown as Record<string, unknown>)[key])}
            onCommit={(v) => saveField(key, 'number', v)} />
        ))}
        <MoneyTile label="Net Amount" primary value={toStr(header.net_amount)} onCommit={(v) => saveField('net_amount', 'number', v)} />
        <MoneyTile label="Item Count" value={toStr(header.item_count)} onCommit={(v) => saveField('item_count', 'number', v)} />
        <MoneyTile label="Total Qty" value={toStr(header.total_quantity)} onCommit={(v) => saveField('total_quantity', 'number', v)} />
      </div>

      {highlights.length > 0 && (
        <div className="mb-2">
          {highlights.map((h) => <span key={h} className="badge text-bg-warning me-1">{h}</span>)}
        </div>
      )}

      {/* ---- Invoice Details ---- */}
      <h6 className="dx-section-title">Invoice Details</h6>
      <div className="dx-fields">
        {INVOICE_FIELDS.map(({ key, label, type }) => (
          <label key={key} className="dx-field">
            <span className="dx-field__label">{label}</span>
            <input
              type={type === 'text' ? 'text' : type}
              className="form-control form-control-sm"
              defaultValue={toStr((header as unknown as Record<string, unknown>)[key])}
              key={`${header.import_id}-${key}-${toStr((header as unknown as Record<string, unknown>)[key])}`}
              onBlur={(e) => saveField(key, type, e.target.value)}
            />
          </label>
        ))}
      </div>
    </div>
  )
}

function isLowConfidenceMatch(header: DocImportRow): boolean {
  return header.supplier_match_confidence != null && header.supplier_match_confidence < 0.6
}

function fmt(n: number): string {
  return n.toLocaleString('en-IN', { maximumFractionDigits: 2 })
}

function MoneyTile({ label, value, primary, onCommit }: { label: string; value: string; primary?: boolean; onCommit: (v: string) => void }) {
  return (
    <label className={`dx-tile${primary ? ' dx-tile--primary' : ''}`}>
      <span className="dx-tile__label">{label}</span>
      <input
        type="number" inputMode="decimal" className="dx-tile__input"
        defaultValue={value} key={value}
        onBlur={(e) => onCommit(e.target.value)}
        onFocus={(e) => e.currentTarget.select()}
      />
    </label>
  )
}
