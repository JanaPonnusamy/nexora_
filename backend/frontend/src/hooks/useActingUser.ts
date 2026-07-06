import { useAuth } from './useAuth'

/**
 * The audit identity (a user GUID) for procurement write operations —
 * created_by / reviewed_by / closed_by / exported_by. These map to
 * UNIQUEIDENTIFIER columns, so the value MUST be a GUID, never a display name.
 *
 * The user is never asked to type an "acting user id": we use the authenticated
 * logged-in user's id automatically. Login is not wired into the SPA yet, so
 * when there is no user we fall back to the platform system-user sentinel
 * (all-zeros GUID, the same sentinel used elsewhere in the backend). Once auth
 * populates `user`, the real user GUID flows through automatically. The result
 * is always a non-empty GUID string, which the backend requires for e.g.
 * opening a Business Cycle.
 */
const SYSTEM_USER_ID = '00000000-0000-0000-0000-000000000000'

export function useActingUser(): string {
  const { user } = useAuth()
  return user?.id || SYSTEM_USER_ID
}
