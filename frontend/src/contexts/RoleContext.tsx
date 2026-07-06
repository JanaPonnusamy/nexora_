import { createContext, useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import type { Role } from '../types/role'
import type { PermissionMatrix } from '../types/permission'
import type { Capability, RoleAccess } from '../types/access'
import { resolveAccess } from '../types/access'
import { roleService } from '../services/roleService'
import { permissionService } from '../services/permissionService'

const STORAGE_KEY = 'nexora.activeRoleId'

export interface RoleContextValue {
  roles: Role[]
  currentRoleId: string | null
  currentRole: Role | null
  setRoleId: (roleId: string | null) => void
  access: RoleAccess
  can: (cap: Capability) => boolean
  landingPath: string
  ready: boolean
}

export const RoleContext = createContext<RoleContextValue | undefined>(undefined)

export function RoleProvider({ children }: { children: ReactNode }) {
  const [roles, setRoles] = useState<Role[]>([])
  const [matrix, setMatrix] = useState<PermissionMatrix | null>(null)
  const [ready, setReady] = useState(false)
  const [currentRoleId, setCurrentRoleId] = useState<string | null>(
    () => window.localStorage.getItem(STORAGE_KEY),
  )

  useEffect(() => {
    let live = true
    Promise.allSettled([roleService.list(), permissionService.getMatrix()])
      .then(([rolesRes, matrixRes]) => {
        if (!live) return
        if (rolesRes.status === 'fulfilled') setRoles(rolesRes.value.filter((r) => r.is_active))
        if (matrixRes.status === 'fulfilled') setMatrix(matrixRes.value)
      })
      .finally(() => live && setReady(true))
    return () => {
      live = false
    }
  }, [])

  const setRoleId = useCallback((roleId: string | null) => {
    setCurrentRoleId(roleId)
    if (roleId) window.localStorage.setItem(STORAGE_KEY, roleId)
    else window.localStorage.removeItem(STORAGE_KEY)
  }, [])

  const currentRole = useMemo(
    () => roles.find((r) => r.role_id === currentRoleId) ?? null,
    [roles, currentRoleId],
  )
  const access = useMemo(() => resolveAccess(currentRole, matrix), [currentRole, matrix])
  const can = useCallback((cap: Capability) => access.permissive || access.caps.has(cap), [access])

  const value = useMemo<RoleContextValue>(
    () => ({
      roles,
      currentRoleId,
      currentRole,
      setRoleId,
      access,
      can,
      landingPath: access.landing,
      ready,
    }),
    [roles, currentRoleId, currentRole, setRoleId, access, can, ready],
  )

  return <RoleContext.Provider value={value}>{children}</RoleContext.Provider>
}
