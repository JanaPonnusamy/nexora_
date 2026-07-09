import { describe, expect, it } from 'vitest'
import { withSessionDefaults, type Session } from './SessionContext'

const session: Session = {
  tenantId: 'tenant-1',
  storeId: 'store-1',
  actingUserId: 'user-guid-1',
}

describe('withSessionDefaults', () => {
  it('injects tenant_id, store_id, and acting_user_id when the caller omits them', () => {
    const merged = withSessionDefaults(session, { search: 'paracetamol' })

    expect(merged).toEqual({
      search: 'paracetamol',
      tenant_id: 'tenant-1',
      store_id: 'store-1',
      acting_user_id: 'user-guid-1',
    })
  })

  it('never overrides a value the caller explicitly supplied', () => {
    const merged = withSessionDefaults(session, {
      tenant_id: 'explicit-tenant',
      store_id: 'explicit-store',
      acting_user_id: 'explicit-user',
    })

    expect(merged).toEqual({
      tenant_id: 'explicit-tenant',
      store_id: 'explicit-store',
      acting_user_id: 'explicit-user',
    })
  })

  it('leaves tenant_id/store_id unset when the session has none, but still injects acting_user_id', () => {
    const anonymousSession: Session = {
      tenantId: null,
      storeId: null,
      actingUserId: '00000000-0000-0000-0000-000000000000',
    }

    const merged = withSessionDefaults(anonymousSession, {})

    expect(merged).toEqual({ acting_user_id: '00000000-0000-0000-0000-000000000000' })
  })
})
