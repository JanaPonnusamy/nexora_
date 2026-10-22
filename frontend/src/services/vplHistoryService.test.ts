import { afterEach, describe, expect, it, vi } from 'vitest'

// Same stub pattern as apiClient.test.ts: avoid pulling in jsdom just to
// satisfy apiClient's bare `localStorage` read on every request.
const store = new Map<string, string>()
vi.stubGlobal('localStorage', {
  getItem: (key: string) => store.get(key) ?? null,
  setItem: (key: string, value: string) => store.set(key, value),
  removeItem: (key: string) => store.delete(key),
})

const { ApiError } = await import('./apiClient')
const { procurementService } = await import('./procurementService')

describe('procurementService VPL history (Phase 2, process-memory backend)', () => {
  const originalFetch = globalThis.fetch

  afterEach(() => {
    globalThis.fetch = originalFetch
    vi.restoreAllMocks()
  })

  it('vplHistoryList calls the real mounted route with tenant/store/limit and returns the headers list', async () => {
    let calledUrl = ''
    globalThis.fetch = vi.fn((url: string) => {
      calledUrl = url
      return Promise.resolve(
        new Response(
          JSON.stringify({ total: 2, returned: 1, headers: [{ history_id: 'h1', tenant_id: 't1', store_id: 's1', cycle_id: 'c1', source_refresh_id: 'r0', rule_snapshot_id: null, created_at: '2026-10-19T00:00:00Z', created_by: 'u1', line_count: 3 }] }),
          { status: 200 },
        ),
      )
    }) as unknown as typeof fetch

    const result = await procurementService.vplHistoryList('t1', 's1', 10)

    expect(calledUrl).toContain('/api/procurement/vpl-history/history')
    expect(calledUrl).toContain('tenant_id=t1')
    expect(calledUrl).toContain('store_id=s1')
    expect(calledUrl).toContain('limit=10')
    expect(result.total).toBe(2)
    expect(result.headers).toHaveLength(1)
    expect(result.headers[0].history_id).toBe('h1')
  })

  it('vplHistoryDetail calls the batch detail route by history_id', async () => {
    let calledUrl = ''
    globalThis.fetch = vi.fn((url: string) => {
      calledUrl = url
      return Promise.resolve(
        new Response(
          JSON.stringify({
            history_id: 'h1', tenant_id: 't1', store_id: 's1', cycle_id: 'c1', source_refresh_id: 'r0',
            rule_snapshot_id: null, created_at: '2026-10-19T00:00:00Z', created_by: 'u1', line_count: 1,
            lines: [{ refresh_id: 'r0', product_code: 'P1', product_id: null, suggested_qty: 5, final_qty: 5, manual_override: false, supplier_code: null, assigned_qty: null, rare_confirmed: false, reviewed_at: null, reason_code: null, row_version: 1, carried_forward: false, updated_by: null, updated_at: null }],
          }),
          { status: 200 },
        ),
      )
    }) as unknown as typeof fetch

    const result = await procurementService.vplHistoryDetail('h1')

    expect(calledUrl).toContain('/api/procurement/vpl-history/history/h1')
    expect(result.lines).toHaveLength(1)
    expect(result.lines[0].product_code).toBe('P1')
  })

  it('surfaces a 403 as an ApiError — the route requires PROCUREMENT_ADMIN, stricter than the page capability', async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve(new Response(JSON.stringify({ detail: 'PROCUREMENT_ADMIN is required.' }), { status: 403 })),
    ) as unknown as typeof fetch

    await expect(procurementService.vplHistoryList('t1', 's1')).rejects.toBeInstanceOf(ApiError)
  })
})
