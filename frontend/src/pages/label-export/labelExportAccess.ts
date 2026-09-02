import type { AuthUser } from '../../types/auth'

// Mirrors backend dependencies.store_scope.assert_label_exporter_store_access:
// only NMW (prints for every store) and super admin/platform users may pick a
// store other than their own; everyone else is locked to their own store.
export function canChangeLabelExportStore(user: AuthUser | null): boolean {
  if (!user) return false
  if (user.isPlatformUser) return true
  if (isSuperAdmin(user)) return true
  return user.storeCode.trim().toUpperCase() === 'NMW'
}

// Only a super admin (or platform user) may approve/reject unit-description
// suggestions submitted from the letter-wise label review grid.
export function isSuperAdmin(user: AuthUser | null): boolean {
  if (!user) return false
  if (user.isPlatformUser) return true
  return user.roleNames.some((name) => name.toLowerCase().replace(/[^a-z]/g, '').includes('superadmin'))
}
