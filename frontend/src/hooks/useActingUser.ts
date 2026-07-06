import { useAuth } from './useAuth'

/** All-zeros system sentinel — used until login is wired, so audit columns get a
 *  valid UNIQUEIDENTIFIER instead of a display name (which SQL cannot convert). */
const SYSTEM_UID = '00000000-0000-0000-0000-000000000000'

/**
 * The audit identity for procurement write operations (created_by / reviewed_by
 * / closed_by / exported_by). The user is never asked to type an "acting user
 * id".
 *
 * It MUST be a GUID: procurement audit columns are `UNIQUEIDENTIFIER`, so a
 * display name (e.g. "Administrator") would fail SQL conversion and 500 the
 * request. Login is not wired into the SPA yet, so this returns the real user id
 * once auth populates it, and the all-zeros system sentinel until then.
 */
export function useActingUser(): string {
  const { user } = useAuth()
  return user?.id || SYSTEM_UID
}
