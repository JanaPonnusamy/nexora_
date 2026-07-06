import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { storeService } from '../../services/storeService'
import type { Store } from '../../types/store'
import { SxSelect } from '../../components/sync/ui'
import '../../components/sync/sync-ui.css'
import '../../components/mapping/mapping-ui.css'
import { ApprovedMappingsTab } from '../../components/mapping/ApprovedMappingsTab'
import { AuditLogTab } from '../../components/mapping/AuditLogTab'
import { AutoMatchesTab } from '../../components/mapping/AutoMatchesTab'
import { DashboardTab } from '../../components/mapping/DashboardTab'
import { ManualReviewTab } from '../../components/mapping/ManualReviewTab'
import { NormalizationDictionaryTab } from '../../components/mapping/NormalizationDictionaryTab'
import { PendingMatchesTab } from '../../components/mapping/PendingMatchesTab'
import { StatisticsTab } from '../../components/mapping/StatisticsTab'
import type { MappingCtx } from '../../components/mapping/shared'

type Tab =
  | 'dashboard' | 'pending' | 'auto' | 'review' | 'approved' | 'dictionary' | 'audit' | 'stats'

const TABS: { key: Tab; label: string; icon: string }[] = [
  { key: 'dashboard', label: 'Dashboard', icon: 'bi-speedometer2' },
  { key: 'pending', label: 'Pending Matches', icon: 'bi-hourglass-split' },
  { key: 'auto', label: 'Auto Matches', icon: 'bi-lightning-charge' },
  { key: 'review', label: 'Manual Review', icon: 'bi-diagram-3' },
  { key: 'approved', label: 'Approved Mappings', icon: 'bi-check2-circle' },
  { key: 'dictionary', label: 'Normalization Dictionary', icon: 'bi-journal-text' },
  { key: 'audit', label: 'Audit Log', icon: 'bi-clock-history' },
  { key: 'stats', label: 'Statistics', icon: 'bi-pie-chart' },
]
const TAB_KEYS = TABS.map((t) => t.key)

export default function ProductMappingPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const param = searchParams.get('tab')
  const activeTab: Tab = (TAB_KEYS as string[]).includes(param ?? '') ? (param as Tab) : 'dashboard'
  const setTab = (tab: Tab) => setSearchParams(tab === 'dashboard' ? {} : { tab }, { replace: true })

  const [stores, setStores] = useState<Store[]>([])
  const [sourceStoreId, setSourceStoreId] = useState('')
  const [targetStoreId, setTargetStoreId] = useState('')

  useEffect(() => {
    storeService.list().then((all) => setStores(all.filter((s) => s.is_active))).catch(() => setStores([]))
  }, [])

  // tenant follows the chosen source store (falls back to the first store).
  const tenantId = useMemo(() => {
    const src = stores.find((s) => s.store_id === sourceStoreId)
    return src?.tenant_id ?? stores[0]?.tenant_id ?? ''
  }, [stores, sourceStoreId])

  const targetOptions = useMemo(
    () => stores.filter((s) => s.tenant_id === tenantId && s.store_id !== sourceStoreId),
    [stores, tenantId, sourceStoreId],
  )

  const label = (id: string) => {
    const s = stores.find((x) => x.store_id === id)
    return s ? `${s.store_code} — ${s.store_name}` : ''
  }

  const ctx: MappingCtx = {
    tenantId,
    sourceStoreId,
    targetStoreId,
    sourceLabel: label(sourceStoreId),
    targetLabel: label(targetStoreId),
  }

  return (
    <div className="sx container-fluid px-0">
      <div className="sx-head">
        <div>
          <div className="sx-head__crumb">Master Data</div>
          <h1 className="sx-head__title">Product Mapping</h1>
          <div className="sx-head__sub">
            Map products across stores with deterministic rules first, fuzzy last, and human
            review for anything uncertain. ProductCode is never a match key on its own.
          </div>
        </div>
        <div className="d-flex gap-2 align-items-center flex-wrap">
          <SxSelect value={sourceStoreId} onChange={(v) => { setSourceStoreId(v); if (v === targetStoreId) setTargetStoreId('') }} ariaLabel="Source store">
            <option value="">Source store…</option>
            {stores.map((s) => <option key={s.store_id} value={s.store_id}>{s.store_code} — {s.store_name}</option>)}
          </SxSelect>
          <i className="bi bi-arrow-right sx-dim" aria-hidden="true" />
          <SxSelect value={targetStoreId} onChange={setTargetStoreId} ariaLabel="Target store">
            <option value="">Target store…</option>
            {targetOptions.map((s) => <option key={s.store_id} value={s.store_id}>{s.store_code} — {s.store_name}</option>)}
          </SxSelect>
        </div>
      </div>

      <div className="sx-tabs" role="tablist" aria-label="Product Mapping sections">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.key}
            className={`sx-tab${activeTab === tab.key ? ' sx-tab--active' : ''}`}
            onClick={() => setTab(tab.key)}
          >
            <i className={`bi ${tab.icon}`} aria-hidden="true" />
            {tab.label}
          </button>
        ))}
      </div>

      <div role="tabpanel">
        {activeTab === 'dashboard' && <DashboardTab ctx={ctx} />}
        {activeTab === 'pending' && <PendingMatchesTab ctx={ctx} />}
        {activeTab === 'auto' && <AutoMatchesTab ctx={ctx} />}
        {activeTab === 'review' && <ManualReviewTab ctx={ctx} />}
        {activeTab === 'approved' && <ApprovedMappingsTab ctx={ctx} />}
        {activeTab === 'dictionary' && <NormalizationDictionaryTab ctx={ctx} />}
        {activeTab === 'audit' && <AuditLogTab ctx={ctx} />}
        {activeTab === 'stats' && <StatisticsTab ctx={ctx} />}
      </div>
    </div>
  )
}
