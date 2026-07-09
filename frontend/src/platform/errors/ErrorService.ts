import { logger } from '../logging/Logger'

export interface PlatformError {
  id: string
  scope: string
  message: string
  cause?: unknown
  timestamp: number
}

type ErrorListener = (error: PlatformError) => void

// Single place unhandled errors surface to, instead of each module rolling
// its own top-level dialog. platform/shell wires one GlobalErrorDialog as the
// default listener (Phase 2.2); modules keep their own inline field-level
// error UI — that's a different, module-owned concern.
class ErrorService {
  private listeners = new Set<ErrorListener>()
  private nextId = 0

  report(scope: string, message: string, cause?: unknown): PlatformError {
    const error: PlatformError = {
      id: `err-${++this.nextId}`,
      scope,
      message,
      cause,
      timestamp: Date.now(),
    }
    logger.error(scope, message, cause)
    this.listeners.forEach((listener) => listener(error))
    return error
  }

  subscribe(listener: ErrorListener): () => void {
    this.listeners.add(listener)
    return () => {
      this.listeners.delete(listener)
    }
  }
}

export const errorService = new ErrorService()
