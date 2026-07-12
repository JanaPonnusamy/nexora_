import type { Role } from './role'
import type { PermissionMatrix } from './permission'

/** Navigation capabilities = permission codes. Access is driven purely by the
 *  permission matrix (role → module) — never by role name. The four procurement
 *  capabilities are separable so future granular permissions keep working. */
export type Capability =
  | 'PLATFORM'
  | 'INVENTORY'
  | 'SYNC'
  | 'ADMINISTRATION'
  | 'REPORTS'
  | 'SETTINGS'
  | 'PRODUCT_MAPPING'
  | 'PROCUREMENT_WORKSPACE'
  | 'PROCUREMENT_ADMIN'
  | 'PROCUREMENT_EXPORT'
  | 'PROCUREMENT_PENDING'
  | 'PROCUREMENT_GRN'
  | 'DOCUMENT_EXTRACTION'
  | 'PASS_GEN'

export const ALL_CAPABILITIES: Capability[] = [
  'PLATFORM', 'INVENTORY', 'SYNC', 'ADMINISTRATION', 'REPORTS', 'SETTINGS',
  'PRODUCT_MAPPING',
  'PROCUREMENT_WORKSPACE', 'PROCUREMENT_ADMIN',
  'PROCUREMENT_EXPORT', 'PROCUREMENT_PENDING', 'PROCUREMENT_GRN',
  'DOCUMENT_EXTRACTION', 'PASS_GEN',
]

const PROCUREMENT_CAPS: Capability[] = [
  'PROCUREMENT_WORKSPACE', 'PROCUREMENT_EXPORT', 'PROCUREMENT_PENDING', 'PROCUREMENT_GRN',
]

/** Map an admin-defined module_code to a capability. Case-insensitive on
 *  substrings so store-defined codes ("procurement_export", "PROC-GRN", …) map
 *  onto the canonical capability set. */
function capForCode(code: string | null | undefined): Capability | null {
  const c = (code ?? '').toUpperCase()
  if (!c) return null
  if (c.includes('PROCUREMENT') || c.includes('PURCHASE')) {
    // Lifecycle administration (Cycle / Refresh management) is a separate,
    // elevated grant from the Purchase Manager workspace.
    if (c.includes('ADMIN') || c.includes('CYCLE') || c.includes('REFRESH')) return 'PROCUREMENT_ADMIN'
    if (c.includes('EXPORT')) return 'PROCUREMENT_EXPORT'
    if (c.includes('PENDING')) return 'PROCUREMENT_PENDING'
    if (c.includes('GRN')) return 'PROCUREMENT_GRN'
    return 'PROCUREMENT_WORKSPACE'
  }
  if (c.includes('PASS')) return 'PASS_GEN'
  if (c.includes('DOCUMENT') || c.includes('EXTRACTION') || c.includes('INVOICE_OCR')) return 'DOCUMENT_EXTRACTION'
  if (c.includes('MAPPING')) return 'PRODUCT_MAPPING'
  if (c.includes('SYNC')) return 'SYNC'
  if (c.includes('STOCK') || c.includes('INVENTORY')) return 'INVENTORY'
  if (c.includes('REPORT')) return 'REPORTS'
  if (c.includes('SETTING')) return 'SETTINGS'
  if (c.includes('MODULE') || c.includes('PERMISSION') || c.includes('ADMIN')) return 'ADMINISTRATION'
  if (c.includes('TENANT') || c.includes('STORE') || c.includes('USER') || c.includes('ROLE') || c.includes('PLATFORM') || c.includes('OVERVIEW')) return 'PLATFORM'
  return null
}

export interface RoleAccess {
  caps: Set<Capability>
  landing: string
  /** True when the role imposes no restriction (see everything). */
  permissive: boolean
}

const PERMISSIVE: RoleAccess = {
  caps: new Set(ALL_CAPABILITIES),
  landing: '/overview',
  permissive: true,
}

/** Resolve effective access for a role from the permission matrix alone.
 *  A role with no configured permissions stays permissive (no lockout while the
 *  matrix is being set up); once permissions exist, they are enforced. */
export function resolveAccess(role: Role | null, matrix: PermissionMatrix | null): RoleAccess {
  if (!role || !matrix) return PERMISSIVE

  const codeById = new Map(matrix.modules.map((m) => [m.module_id, m.module_code]))
  const caps = new Set<Capability>()
  for (const a of matrix.assignments) {
    if (a.role_id !== role.role_id) continue
    const cap = capForCode(codeById.get(a.module_id))
    if (cap) caps.add(cap)
  }

  if (caps.size === 0) return PERMISSIVE

  // A Procurement Admin (Cycle/Refresh management) can also open the Purchase
  // Manager workspace, so the nav group renders for admins.
  if (caps.has('PROCUREMENT_ADMIN')) caps.add('PROCUREMENT_WORKSPACE')

  // A single coarse "procurement" grant unlocks the whole workspace; explicit
  // finer grants (export/pending/grn) are respected but always imply workspace.
  if (PROCUREMENT_CAPS.some((c) => caps.has(c))) {
    caps.add('PROCUREMENT_WORKSPACE')
    const hasFiner = caps.has('PROCUREMENT_EXPORT') || caps.has('PROCUREMENT_PENDING') || caps.has('PROCUREMENT_GRN')
    if (!hasFiner) {
      caps.add('PROCUREMENT_EXPORT')
      caps.add('PROCUREMENT_PENDING')
      caps.add('PROCUREMENT_GRN')
    }
  }

  const landing = caps.has('PLATFORM')
    ? '/overview'
    : caps.has('PROCUREMENT_WORKSPACE')
      ? '/procurement/workspace'
      : '/overview'
  return { caps, landing, permissive: false }
}
