import { afterEach, describe, expect, it } from 'vitest'
import { VPL_HISTORY_SCREEN_STORAGE_KEY, isVplHistoryScreenEnabled } from './vplHistoryFlag'
import {
  applyFailure,
  applySaveFailure,
  applySaveSuccess,
  applyVersionConflict,
  applyWorking,
  attemptProhibited,
  confirmRefresh,
  createScreen,
  displayQty,
  moveSelection,
  requestRefresh,
  retry,
  switchContext,
  type VplScreenLine,
  type VplWorkingBody,
} from './vplHistorySession'

const store = new Map<string, string>()
const memoryStorage = {
  getItem: (key: string) => store.get(key) ?? null,
  setItem: (key: string, value: string) => { store.set(key, value) },
  removeItem: (key: string) => { store.delete(key) },
}

function line(code: string, extra: Partial<VplScreenLine> = {}): VplScreenLine {
  return {
    product_code: code,
    product_id: null,
    suggested_qty: 5,
    final_qty: 5,
    manual_override: false,
    supplier_code: null,
    assigned_qty: null,
    rare_confirmed: false,
    reviewed_at: null,
    reason_code: null,
    row_version: 1,
    carried_forward: false,
    orderable: true,
    updated_by: null,
    updated_at: null,
    ...extra,
  }
}

function working(storeId: string, lines: VplScreenLine[], removed: VplScreenLine[] = [], cycleId = 'c1'): VplWorkingBody {
  return {
    tenant_id: 't1',
    store_id: storeId,
    cycle_id: cycleId,
    refresh_id: 'r1',
    rule_snapshot_id: 'snap',
    lines,
    removed_manual_review: {
      section: 'Removed from Current Suggestions — Manual Review',
      orderable: false,
      lines: removed,
    },
  }
}

describe('VPL history screen session', () => {
  afterEach(() => store.clear())

  it('defaults the feature flag off', () => {
    expect(isVplHistoryScreenEnabled()).toBe(false)
    memoryStorage.setItem(VPL_HISTORY_SCREEN_STORAGE_KEY, '1')
    globalThis.localStorage = memoryStorage as unknown as Storage
    expect(isVplHistoryScreenEnabled()).toBe(true)
  })

  it('stays disabled and does not load when the flag is off', () => {
    const screen = createScreen('t1', 's1', 'c1', false)
    expect(screen.status).toBe('disabled')
    expect(screen.lines).toEqual([])
    expect(retry(screen).status).toBe('disabled')
  })

  it('shows loading with an empty grid, then empty or ready', () => {
    const loading = createScreen('t1', 's1', 'c1', true)
    expect(loading.status).toBe('loading')
    expect(loading.lines).toEqual([])
    const empty = applyWorking(loading, loading.requestId, working('s1', []), [])
    expect(empty.status).toBe('empty')
    const ready = applyWorking(loading, loading.requestId, working('s1', [line('A')]), [])
    expect(ready.status).toBe('ready')
    expect(ready.selectedCode).toBe('A')
  })

  it('clears the previous store immediately and ignores a late response', () => {
    const first = applyWorking(createScreen('t1', 's1', 'c1', true), 1, working('s1', [line('A')]), [])
    const next = switchContext(first, 't1', 's2', 'c2')
    expect(next.lines).toEqual([])
    expect(next.selectedCode).toBeNull()
    expect(next.status).toBe('loading')
    const late = applyWorking(next, first.requestId, working('s1', [line('OLD')]), [])
    expect(late.lines).toEqual([])
    expect(late.storeId).toBe('s2')
    const failed = applyFailure(next, next.requestId, 'unavailable')
    expect(failed.status).toBe('error')
    expect(failed.lines).toEqual([])
    const again = retry(failed)
    const recovered = applyWorking(again, again.requestId, working('s2', [line('B')], [], 'c2'), [])
    expect(recovered.lines.map((row) => row.product_code)).toEqual(['B'])
  })

  it('records a quantity save only after success and does not invent a zero', () => {
    const ready = applyWorking(createScreen('t1', 's1', 'c1', true), 1, working('s1', [line('A', { final_qty: null })]), [])
    expect(displayQty(ready.lines[0].final_qty)).toBe('unavailable')
    const failed = applySaveFailure(ready)
    expect(failed.saved).toBe(false)
    expect(failed.lines[0].final_qty).toBeNull()
    const saved = applySaveSuccess(ready, 'A', 9, 2)
    expect(saved.saved).toBe(true)
    expect(saved.lines[0].final_qty).toBe(9)
    expect(saved.lines[0].row_version).toBe(2)
  })

  it('shows a version conflict and does not auto-retry the write', () => {
    const ready = applyWorking(createScreen('t1', 's1', 'c1', true), 1, working('s1', [line('A', { row_version: 4 })]), [])
    const conflict = applyVersionConflict(ready)
    expect(conflict.status).toBe('conflict')
    expect(conflict.saved).toBe(false)
    expect(conflict.lines[0].row_version).toBe(4)
    expect(conflict.conflict).toMatch(/Reload/)
  })

  it('asks before refresh when a manual edit or removed line exists', () => {
    const plain = applyWorking(createScreen('t1', 's1', 'c1', true), 1, working('s1', [line('A')]), [])
    expect(requestRefresh(plain).refreshNeedsConfirm).toBe(false)
    const manual = applyWorking(createScreen('t1', 's1', 'c1', true), 1, working('s1', [line('A', { manual_override: true })]), [])
    const asked = requestRefresh(manual)
    expect(asked.refreshNeedsConfirm).toBe(true)
    expect(asked.status).toBe('ready')
    const started = confirmRefresh(asked)
    expect(started.status).toBe('loading')
    expect(started.lines).toEqual([])
  })

  it('keeps history read-only and focuses the first row, including keyboard move', () => {
    const ready = applyWorking(
      createScreen('t1', 's1', 'c1', true),
      1,
      working('s1', [line('A'), line('B')]),
      [{ history_id: 'h1', rule_snapshot_id: 'snap', line_count: 2, created_at: '2026-10-19T00:00:00Z' }],
    )
    expect(ready.historyReadOnly).toBe(true)
    expect(ready.history).toHaveLength(1)
    expect(ready.selectedCode).toBe('A')
    expect(moveSelection(ready, 1).selectedCode).toBe('B')
  })

  it('keeps a removed line out of the orderable section and rejects ordering it', () => {
    const removed = line('A', { orderable: false, final_qty: 9, supplier_code: 'SUP' })
    const ready = applyWorking(createScreen('t1', 's1', 'c1', true), 1, working('s1', [line('B')], [removed]), [])
    expect(ready.lines.map((row) => row.product_code)).toEqual(['B'])
    expect(ready.removedSection).toBe('Manual Review — Removed From Latest Generation')
    expect(ready.removed[0].orderable).toBe(false)
    expect(attemptProhibited(ready.removed[0])).toEqual({ accepted: false, code: 'NOT_ORDERABLE' })
  })
})
