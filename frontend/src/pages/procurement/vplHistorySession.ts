/** In-memory screen state for /api/procurement/vpl-history. No live generation. */

export interface VplScreenLine {
  product_code: string
  product_id: string | null
  suggested_qty: number | null
  final_qty: number | null
  manual_override: boolean
  supplier_code: string | null
  assigned_qty: number | null
  rare_confirmed: boolean
  reviewed_at: string | null
  reason_code: string | null
  row_version: number
  carried_forward: boolean
  orderable: boolean
  updated_by: string | null
  updated_at: string | null
}

export interface VplWorkingBody {
  tenant_id: string
  store_id: string
  cycle_id: string
  refresh_id: string
  rule_snapshot_id: string | null
  lines: VplScreenLine[]
  removed_manual_review: {
    section: string
    orderable: false
    lines: VplScreenLine[]
  }
}

export interface VplHistoryHeader {
  history_id: string
  rule_snapshot_id: string | null
  line_count: number
  created_at: string
}

export type VplScreenStatus = 'disabled' | 'loading' | 'ready' | 'empty' | 'error' | 'conflict'

export interface VplScreenState {
  requestId: number
  tenantId: string
  storeId: string
  cycleId: string
  status: VplScreenStatus
  refreshId: string | null
  ruleSnapshotId: string | null
  lines: VplScreenLine[]
  removed: VplScreenLine[]
  removedSection: string
  history: VplHistoryHeader[]
  selectedCode: string | null
  error: string | null
  conflict: string | null
  saved: boolean
  refreshNeedsConfirm: boolean
  historyReadOnly: true
}

export function displayQty(value: number | null): string {
  return value == null ? 'unavailable' : String(value)
}

export function createScreen(tenantId: string, storeId: string, cycleId: string, enabled: boolean): VplScreenState {
  return {
    requestId: enabled ? 1 : 0,
    tenantId,
    storeId,
    cycleId,
    status: enabled ? 'loading' : 'disabled',
    refreshId: null,
    ruleSnapshotId: null,
    lines: [],
    removed: [],
    removedSection: 'Manual Review — Removed From Latest Generation',
    history: [],
    selectedCode: null,
    error: null,
    conflict: null,
    saved: false,
    refreshNeedsConfirm: false,
    historyReadOnly: true,
  }
}

export function switchContext(state: VplScreenState, tenantId: string, storeId: string, cycleId: string): VplScreenState {
  if (state.status === 'disabled') return { ...createScreen(tenantId, storeId, cycleId, false) }
  return {
    ...createScreen(tenantId, storeId, cycleId, true),
    requestId: state.requestId + 1,
  }
}

export function applyWorking(state: VplScreenState, requestId: number, body: VplWorkingBody, history: VplHistoryHeader[]): VplScreenState {
  if (requestId !== state.requestId) return state
  if (body.store_id !== state.storeId || body.cycle_id !== state.cycleId) return state
  const lines = body.lines
  const removed = body.removed_manual_review.lines
  const selected = lines[0]?.product_code ?? removed[0]?.product_code ?? null
  return {
    ...state,
    status: lines.length === 0 && removed.length === 0 ? 'empty' : 'ready',
    refreshId: body.refresh_id,
    ruleSnapshotId: body.rule_snapshot_id,
    lines,
    removed,
    removedSection: 'Manual Review — Removed From Latest Generation',
    history,
    selectedCode: selected,
    error: null,
    conflict: null,
    saved: false,
    refreshNeedsConfirm: false,
  }
}

export function applyFailure(state: VplScreenState, requestId: number, message: string): VplScreenState {
  if (requestId !== state.requestId) return state
  return {
    ...state,
    status: 'error',
    lines: [],
    removed: [],
    history: [],
    selectedCode: null,
    refreshId: null,
    error: message,
    saved: false,
  }
}

export function retry(state: VplScreenState): VplScreenState {
  if (state.status === 'disabled') return state
  return { ...switchContext(state, state.tenantId, state.storeId, state.cycleId), requestId: state.requestId + 1 }
}

export function moveSelection(state: VplScreenState, delta: number): VplScreenState {
  const codes = [...state.lines, ...state.removed].map((line) => line.product_code)
  if (codes.length === 0) return state
  const index = Math.max(0, codes.indexOf(state.selectedCode ?? codes[0]))
  const next = codes[(index + delta + codes.length) % codes.length]
  return { ...state, selectedCode: next }
}

export function requestRefresh(state: VplScreenState): VplScreenState {
  const manual = state.lines.some((line) => line.manual_override) || state.removed.length > 0
  if (!manual) return { ...state, refreshNeedsConfirm: false }
  return { ...state, refreshNeedsConfirm: true }
}

export function confirmRefresh(state: VplScreenState): VplScreenState {
  return { ...state, refreshNeedsConfirm: false, status: 'loading', lines: [], removed: [], selectedCode: null, requestId: state.requestId + 1, saved: false }
}

export function applySaveSuccess(state: VplScreenState, productCode: string, finalQty: number, rowVersion: number): VplScreenState {
  return {
    ...state,
    saved: true,
    conflict: null,
    lines: state.lines.map((line) =>
      line.product_code === productCode
        ? { ...line, final_qty: finalQty, manual_override: true, row_version: rowVersion }
        : line,
    ),
  }
}

export function applySaveFailure(state: VplScreenState): VplScreenState {
  return { ...state, saved: false }
}

export function applyVersionConflict(state: VplScreenState): VplScreenState {
  return {
    ...state,
    status: 'conflict',
    saved: false,
    conflict: 'This line changed. Reload the working set before editing again.',
  }
}

export function attemptProhibited(line: VplScreenLine): { accepted: false; code: 'NOT_ORDERABLE' } {
  if (line.orderable) {
    throw new Error('Active lines are not rejected by this guard.')
  }
  return { accepted: false, code: 'NOT_ORDERABLE' }
}
