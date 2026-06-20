import { useCallback, useEffect, useState } from 'react'
import type { Module } from '../types/module'
import { moduleService } from '../services/moduleService'

export function useModule(moduleId: string | undefined) {
  const [module, setModule] = useState<Module | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!moduleId) {
      return
    }
    setIsLoading(true)
    setError(null)
    try {
      setModule(await moduleService.getById(moduleId))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load module')
    } finally {
      setIsLoading(false)
    }
  }, [moduleId])

  useEffect(() => {
    void load()
  }, [load])

  return { module, isLoading, error, reload: load }
}
