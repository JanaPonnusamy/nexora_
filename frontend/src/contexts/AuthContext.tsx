import { createContext, useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import type { AuthContextValue, AuthUser } from '../types/auth'
import { tokenStorage } from '../services/tokenStorage'
import { api } from '../services/apiClient'

export const AuthContext = createContext<AuthContextValue | undefined>(undefined)

interface MeResponse {
  user_id: string
  username: string
  first_name: string
  tenant_id: string | null
  is_platform_user: boolean
  roles: { role_name: string; store_id: string; store_code: string }[]
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => tokenStorage.get())
  const [user, setUser] = useState<AuthUser | null>(null)
  const [restoring, setRestoring] = useState<boolean>(() => Boolean(tokenStorage.get()))

  const login = useCallback((nextToken: string, nextUser: AuthUser) => {
    tokenStorage.set(nextToken)
    setToken(nextToken)
    setUser(nextUser)
  }, [])

  const logout = useCallback(() => {
    tokenStorage.clear()
    setToken(null)
    setUser(null)
  }, [])

  // A stored token survives a page reload but component state doesn't - refetch
  // the user so `user.id` (procurement audit columns, role resolution) isn't
  // null while still "authenticated". An expired/invalid token 401s and we log
  // out cleanly rather than leaving a half-authenticated state.
  useEffect(() => {
    if (!token || user) {
      setRestoring(false)
      return
    }
    let live = true
    api
      .get<MeResponse>('/api/auth/me')
      .then((me) => {
        if (!live) return
        const primaryRole = me.roles?.[0]
        setUser({
          id: me.user_id,
          username: me.username,
          fullName: me.first_name,
          tenant: me.tenant_id ?? '',
          isPlatformUser: me.is_platform_user,
          roleNames: (me.roles ?? []).map((r) => r.role_name),
          storeId: primaryRole?.store_id ?? '',
          storeCode: primaryRole?.store_code ?? '',
        })
      })
      .catch(() => {
        if (live) logout()
      })
      .finally(() => live && setRestoring(false))
    return () => {
      live = false
    }
  }, [token, user, logout])

  const isAuthenticated = Boolean(token) && !restoring

  const value = useMemo<AuthContextValue>(
    () => ({ user, token, isAuthenticated, restoring, login, logout }),
    [user, token, isAuthenticated, restoring, login, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
