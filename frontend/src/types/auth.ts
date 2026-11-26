export interface AuthUser {
  id: string
  username: string
  fullName: string
  tenant: string
  isPlatformUser: boolean
  roleNames: string[]
  storeId: string
  storeCode: string
}

export interface AuthContextValue {
  user: AuthUser | null
  token: string | null
  isAuthenticated: boolean
  /** True only while a page-reload restore of a stored token is in flight. */
  restoring: boolean
  login: (token: string, user: AuthUser) => void
  logout: () => void
  /** Identifies this running app to pages that behave differently when
   *  embedded elsewhere (e.g. QuickStockPage's public-kiosk vs
   *  signed-in-session branch). Always 'nextech-mediq' here — this IS
   *  NexTech MedIQ, the main Nexora web app. */
  host: string
}
