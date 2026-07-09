export type NotificationVariant = 'success' | 'info' | 'warning' | 'error'

export interface Notification {
  id: string
  variant: NotificationVariant
  message: string
}

type Listener = (notification: Notification) => void

/**
 * General-purpose, user-facing toast service ("Purchase order saved",
 * "Import complete") — distinct from ErrorService, which is for unhandled
 * failures surfaced through GlobalErrorDialog. The existing
 * components/stock/Toast.tsx is explicitly self-contained (its own comment:
 * "the platform has no toast system yet"); this is that system.
 */
class NotificationService {
  private listeners = new Set<Listener>()
  private nextId = 0

  notify(variant: NotificationVariant, message: string): Notification {
    const notification: Notification = { id: `note-${++this.nextId}`, variant, message }
    this.listeners.forEach((listener) => listener(notification))
    return notification
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener)
    return () => {
      this.listeners.delete(listener)
    }
  }
}

export const notificationService = new NotificationService()

export const notify = {
  success: (message: string) => notificationService.notify('success', message),
  info: (message: string) => notificationService.notify('info', message),
  warning: (message: string) => notificationService.notify('warning', message),
  error: (message: string) => notificationService.notify('error', message),
}
