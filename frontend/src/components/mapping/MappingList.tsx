import { useCallback, useEffect, useState } from 'react'
import { productMappingService } from '../../services/productMappingService'
import type { Mapping, MappingStatus } from '../../types/productMapping'
import { EmptyState } from '../common/EmptyState'
import { ErrorState } from '../common/ErrorState'
import { TableSkeleton } from '../common/TableSkeleton'
import { SxCard, SxCardBody, SxCardHead, SxPager, SxSearch, SxTable } from '../sync/ui'
import { AttrCell, ConfidenceChip, MethodChip, ProductCell, StatusChip, type MappingCtx } from './shared'

const PAGE_SIZE = 25

/** Read-only paginated list of mappings for one status (Pending / Auto / Approved). */
export function MappingList({
  ctx, status, title, icon, emptyHint,
}: { ctx: MappingCtx; status: MappingStatus; title: string; icon: string; emptyHint: string }) {
  const [items, setItems] = useState<Mapping[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    productMappingService
      .mappings(ctx.tenantId, {
        status,
        source_store_id: ctx.sourceStoreId,
        target_store_id: ctx.targetStoreId,
        search,
        page,
        page_size: PAGE_SIZE,
      })
      .then((res) => { setItems(res.items); setTotal(res.total) })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load mappings'))
      .finally(() => setLoading(false))
  }, [ctx.tenantId, ctx.sourceStoreId, ctx.targetStoreId, status, search, page])

  useEffect(() => { load() }, [load])

  return (
    <SxCard>
      <SxCardHead title={title} icon={icon} sub={`${total} mapping${total === 1 ? '' : 's'}`}
        action={<SxSearch value={search} onChange={(v) => { setPage(1); setSearch(v) }} placeholder="Search source product…" />} />
      <SxCardBody flush>
        {loading ? <TableSkeleton rows={6} columns={6} />
          : error ? <ErrorState description={error} onRetry={load} />
          : items.length === 0 ? <EmptyState icon={icon} title={`No ${status.toLowerCase()} mappings`} description={emptyHint} />
          : (
            <>
              <SxTable>
                <thead>
                  <tr>
                    <th>Source Product</th><th>Attributes</th><th>Target Product</th>
                    <th>Method</th><th className="sx-num">Confidence</th><th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((m) => (
                    <tr key={m.mapping_id}>
                      <td><ProductCell code={m.source_product_code} name={m.source_product_name} /></td>
                      <td><AttrCell m={m} /></td>
                      <td><ProductCell code={m.target_product_code} name={m.target_product_name} /></td>
                      <td><MethodChip method={m.match_method} /></td>
                      <td className="sx-num"><ConfidenceChip value={m.confidence} /></td>
                      <td><StatusChip status={m.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </SxTable>
              <SxPager
                rangeStart={total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1}
                rangeEnd={Math.min(total, page * PAGE_SIZE)}
                total={total}
                page={page - 1}
                totalPages={Math.max(1, Math.ceil(total / PAGE_SIZE))}
                onPage={(p) => setPage(p + 1)}
                noun="mappings"
              />
            </>
          )}
      </SxCardBody>
    </SxCard>
  )
}
