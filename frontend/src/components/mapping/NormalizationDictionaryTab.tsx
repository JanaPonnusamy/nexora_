import { useCallback, useEffect, useState } from 'react'
import { useActingUser } from '../../hooks/useActingUser'
import { productMappingService } from '../../services/productMappingService'
import type { DictionaryEntry } from '../../types/productMapping'
import { EmptyState } from '../common/EmptyState'
import { ErrorState } from '../common/ErrorState'
import { TableSkeleton } from '../common/TableSkeleton'
import { SxButton, SxCard, SxCardBody, SxCardHead, SxChip, SxSelect, SxTable } from '../sync/ui'
import type { MappingCtx } from './shared'

const KINDS = ['DOSAGE_FORM', 'UNIT', 'NOISE']

export function NormalizationDictionaryTab({ ctx }: { ctx: MappingCtx }) {
  const actingUser = useActingUser()
  const [rows, setRows] = useState<DictionaryEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [term, setTerm] = useState('')
  const [canonical, setCanonical] = useState('')
  const [kind, setKind] = useState('DOSAGE_FORM')
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    productMappingService.dictionary(ctx.tenantId || undefined)
      .then(setRows)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load dictionary'))
      .finally(() => setLoading(false))
  }, [ctx.tenantId])

  useEffect(() => { load() }, [load])

  const addTerm = async () => {
    if (!term.trim()) return
    setBusy(true)
    try {
      await productMappingService.addTerm(
        { term: term.trim(), canonical: canonical.trim() || undefined, kind, actor: actingUser || null },
        ctx.tenantId || undefined,
      )
      setTerm(''); setCanonical('')
      load()
    } finally { setBusy(false) }
  }

  const toggle = async (e: DictionaryEntry) => {
    await productMappingService.updateTerm(e.entry_id, { is_active: !e.is_active, actor: actingUser || null })
    load()
  }

  const remove = async (e: DictionaryEntry) => {
    await productMappingService.deleteTerm(e.entry_id)
    load()
  }

  return (
    <SxCard>
      <SxCardHead title="Normalization Dictionary" icon="bi-journal-text" sub={`${rows.length} terms`} />
      <SxCardBody>
        <div className="d-flex gap-2 flex-wrap align-items-center mb-3">
          <input className="sx-input" style={{ maxWidth: 180 }} placeholder="Term (e.g. TABLET)"
            value={term} onChange={(ev) => setTerm(ev.target.value.toUpperCase())} aria-label="Term" />
          <input className="sx-input" style={{ maxWidth: 180 }} placeholder="Canonical (e.g. TAB)"
            value={canonical} onChange={(ev) => setCanonical(ev.target.value.toUpperCase())} aria-label="Canonical" />
          <SxSelect value={kind} onChange={setKind} ariaLabel="Kind">
            {KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
          </SxSelect>
          <SxButton variant="primary" icon="bi-plus-lg" busy={busy} disabled={!term.trim()} onClick={addTerm}>Add term</SxButton>
        </div>

        {loading ? <TableSkeleton rows={6} columns={4} />
          : error ? <ErrorState description={error} onRetry={load} />
          : rows.length === 0 ? <EmptyState icon="bi-journal-text" title="No terms" description="Add dosage-form, unit or noise words to tune normalization." />
          : (
            <SxTable>
              <thead><tr><th>Term</th><th>Canonical</th><th>Kind</th><th>Scope</th><th>Status</th><th></th></tr></thead>
              <tbody>
                {rows.map((e) => (
                  <tr key={e.entry_id}>
                    <td><strong>{e.term}</strong></td>
                    <td>{e.canonical ?? '—'}</td>
                    <td><SxChip tone="default">{e.kind}</SxChip></td>
                    <td>{e.tenant_id ? <SxChip tone="indigo">Tenant</SxChip> : <SxChip tone="muted">Global</SxChip>}</td>
                    <td>{e.is_active ? <SxChip tone="success" dot>Active</SxChip> : <SxChip tone="muted">Inactive</SxChip>}</td>
                    <td>
                      <div className="d-flex gap-1 justify-content-end">
                        <SxButton variant="ghost" sm icon={e.is_active ? 'bi-pause' : 'bi-play'} onClick={() => toggle(e)} title={e.is_active ? 'Disable' : 'Enable'} />
                        {e.tenant_id && <SxButton variant="danger" sm icon="bi-trash" onClick={() => remove(e)} title="Delete" />}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </SxTable>
          )}
      </SxCardBody>
    </SxCard>
  )
}
