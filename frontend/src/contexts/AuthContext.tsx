import { createContext, useCallback, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import type { AuthContextValue, AuthUser } from '../types/auth'
import { tokenStorage } from '../services/tokenStorage'

export const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => tokenStorage.get())
  const [user, setUser] = useState<AuthUser | null>(null)

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

  // UI-01B: the login screen is not implemented yet, so the shell stays open
  // for development. Replace this with `Boolean(token)` once auth is wired up.
  const isAuthenticated = true

  const value = useMemo<AuthContextValue>(
    () => ({ user, token, isAuthenticated, login, logout }),
    [user, token, login, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
