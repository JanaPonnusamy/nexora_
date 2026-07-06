import { useCallback, useRef, useState } from 'react'

export type ToastTone = 'success' | 'danger' | 'info'

export interface Toast {
  id: number
  tone: ToastTone
  message: string
}

const ICONS: Record<ToastTone, string> = {
  success: 'bi-check-circle',
  danger: 'bi-exclamation-triangle',
  info: 'bi-info-circle',
}

/** Minimal self-contained toast stack (the platform has no toast system yet). */
export function useToasts() {
  const [toasts, setToasts] = useState<Toast[]>([])
  const nextId = useRef(1)

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id))
  }, [])

  const push = useCallback(
    (tone: ToastTone, message: string) => {
      const id = nextId.current++
      setToasts((current) => [...current, { id, tone, message }])
      window.setTimeout(() => dismiss(id), 4000)
    },
    [dismiss],
  )

  return { toasts, push, dismiss }
}

export function ToastStack({ toasts, onDismiss }: { toasts: Toast[]; onDismiss: (id: number) => void }) {
  return (
    <div className="sa-toasts" aria-live="polite" aria-atomic="true">
      {toasts.map((toast) => (
        <div key={toast.id} className={`sa-toast sa-toast--${toast.tone}`} role="status">
          <i className={`bi ${ICONS[toast.tone]}`} aria-hidden="true" />
          <span className="sa-toast__msg">{toast.message}</span>
          <button type="button" className="sa-toast__close" aria-label="Dismiss" onClick={() => onDismiss(toast.id)}>
            <i className="bi bi-x" aria-hidden="true" />
          </button>
        </div>
      ))}
    </div>
  )
}
