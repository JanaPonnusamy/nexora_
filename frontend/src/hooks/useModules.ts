import { useCallback, useEffect, useState } from 'react'
import type { Module } from '../types/module'
import { moduleService } from '../services/moduleService'

export function useModules() {
  const [modules, setModules] = useState<Module[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      setModules(await moduleService.list())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load modules')
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  return { modules, isLoading, error, reload: load }
}
