import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

// Centralizes what's manually threaded on nearly every backend call today —
// tenant_id, store_id, and an acting-user GUID (see useActingUser.ts's
// all-zeros sentinel pattern) — so modules built on the platform stop
// repeating it per call site. Purely additive: existing services keep passing
// these explicitly and are unaffected.
export interface Session {
  tenantId: string | null
  storeId: string | null
  actingUserId: string
}

const ANONYMOUS_ACTING_USER = '00000000-0000-0000-0000-000000000000'

const defaultSession: Session = {
  tenantId: null,
  storeId: null,
  actingUserId: ANONYMOUS_ACTING_USER,
}

interface SessionContextValue extends Session {
  setTenantId: (tenantId: string | null) => void
  setStoreId: (storeId: string | null) => void
}

const SessionContext = createContext<SessionContextValue | undefined>(undefined)

let sessionSnapshot: Session = defaultSession

/**
 * Non-React accessor for code outside the component tree (e.g. a future
 * apiClient.ts interceptor) that needs the current session without being a
 * hook consumer itself.
 */
export function getSessionSnapshot(): Session {
  return sessionSnapshot
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [tenantId, setTenantId] = useState<string | null>(defaultSession.tenantId)
  const [storeId, setStoreId] = useState<string | null>(defaultSession.storeId)
  const actingUserId = defaultSession.actingUserId

  // Mutating the module-level snapshot belongs in an effect (synchronizing
  // an external accessor with committed React state), not during render.
  useEffect(() => {
    sessionSnapshot = { tenantId, storeId, actingUserId }
  }, [tenantId, storeId, actingUserId])

  const value = useMemo<SessionContextValue>(
    () => ({ tenantId, storeId, actingUserId, setTenantId, setStoreId }),
    [tenantId, storeId, actingUserId],
  )

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}

export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext)
  if (!ctx) throw new Error('useSession must be used within a SessionProvider')
  return ctx
}

/**
 * Pure merge helper: fills session defaults into a params object without
 * overriding anything the caller explicitly supplied. This is what a future
 * apiClient.ts interceptor calls — kept separate and pure so it's testable
 * without mounting React.
 */
export function withSessionDefaults(
  session: Session,
  params: Record<string, string | undefined>,
): Record<string, string | undefined> {
  const merged: Record<string, string | undefined> = { ...params }
  if (merged.tenant_id === undefined && session.tenantId) merged.tenant_id = session.tenantId
  if (merged.store_id === undefined && session.storeId) merged.store_id = session.storeId
  if (merged.acting_user_id === undefined) merged.acting_user_id = session.actingUserId
  return merged
}
