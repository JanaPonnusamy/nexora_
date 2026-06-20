export interface AuthUser {
  id: string
  username: string
  fullName: string
  tenant: string
}

export interface AuthContextValue {
  user: AuthUser | null
  token: string | null
  isAuthenticated: boolean
  login: (token: string, user: AuthUser) => void
  logout: () => void
}
