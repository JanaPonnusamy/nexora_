import { useEffect, useState } from 'react'
import { notificationService, type Notification, type NotificationVariant } from './notificationService'

const AUTO_DISMISS_MS = 5000

const ICONS: Record<NotificationVariant, string> = {
  success: 'bi-check-circle-fill',
  info: 'bi-info-circle-fill',
  warning: 'bi-exclamation-triangle-fill',
  error: 'bi-x-circle-fill',
}

/**
 * Host component for `notify.*()` calls — mount once (see PlatformShell).
 * Modules call notify.success()/info()/warning()/error() instead of
 * building their own toast stack.
 */
export function UniNotification() {
  const [notifications, setNotifications] = useState<Notification[]>([])

  useEffect(() => {
    return notificationService.subscribe((notification) => {
      setNotifications((prev) => [...prev, notification])
      setTimeout(() => {
        setNotifications((prev) => prev.filter((existing) => existing.id !== notification.id))
      }, AUTO_DISMISS_MS)
    })
  }, [])

  if (notifications.length === 0) return null

  return (
    <div className="uni-notification-stack" role="status" aria-live="polite">
      {notifications.map((notification) => (
        <div key={notification.id} className={`uni-notification uni-notification--${notification.variant}`}>
          <i className={`bi ${ICONS[notification.variant]}`} aria-hidden="true" />
          <span className="uni-notification__message">{notification.message}</span>
          <button
            type="button"
            className="btn-close"
            aria-label="Dismiss"
            onClick={() =>
              setNotifications((prev) => prev.filter((existing) => existing.id !== notification.id))
            }
          />
        </div>
      ))}
    </div>
  )
}
