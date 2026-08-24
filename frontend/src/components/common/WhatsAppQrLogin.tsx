import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../../services/apiClient'
import { whatsappService } from '../../services/whatsappService'
import './whatsapp-qr-login.css'

interface WhatsAppQrLoginProps {
  profileId: string
  /** Called once the profile becomes logged in (after a successful scan). */
  onLoggedIn?: () => void
  onClose: () => void
}

/**
 * Shows the WhatsApp Web login QR **inside the user's own browser** by fetching
 * a server-captured PNG of the QR canvas. Needed because the backend runs on a
 * remote/HO host, so the Playwright-driven Firefox window (where the QR is
 * normally rendered) is never visible to the operator. Polls the same endpoint
 * on an interval so an expired QR is refreshed automatically and a completed
 * scan is detected without a manual retry.
 */
export function WhatsAppQrLogin({ profileId, onLoggedIn, onClose }: WhatsAppQrLoginProps) {
  const [qr, setQr] = useState<string | null>(null)
  const [loggedIn, setLoggedIn] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const timerRef = useRef<number | null>(null)
  const doneRef = useRef(false)

  const poll = useCallback(async () => {
    try {
      const result = await whatsappService.loginQr(profileId)
      setError('')
      if (result.logged_in) {
        setLoggedIn(true)
        setQr(null)
        if (!doneRef.current) {
          doneRef.current = true
          onLoggedIn?.()
        }
        return
      }
      setQr(result.qr_data_uri)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to load the WhatsApp QR code.')
    } finally {
      setLoading(false)
    }
  }, [profileId, onLoggedIn])

  useEffect(() => {
    if (!profileId) return
    void poll()
    // WhatsApp rotates the QR roughly every ~20s and login can complete at any
    // moment; re-poll every 4s to refresh the image and catch a finished scan.
    timerRef.current = window.setInterval(() => {
      if (!doneRef.current) void poll()
    }, 4000)
    return () => {
      if (timerRef.current !== null) window.clearInterval(timerRef.current)
    }
  }, [profileId, poll])

  return (
    <div className="wa-qr__backdrop" role="dialog" aria-modal="true" onClick={onClose}>
      <div className="wa-qr__card" onClick={(event) => event.stopPropagation()}>
        <div className="wa-qr__head">
          <h3>Link WhatsApp</h3>
          <button type="button" className="btn-close btn-close-white" aria-label="Close" onClick={onClose} />
        </div>

        {error && <div className="alert alert-danger mb-0">{error}</div>}

        {loggedIn ? (
          <div className="wa-qr__done">
            <i className="bi bi-check-circle-fill" />
            <div>
              <strong>WhatsApp is linked.</strong>
              <div className="wa-qr__hint">You can close this and send now.</div>
            </div>
          </div>
        ) : (
          <>
            <ol className="wa-qr__steps">
              <li>Open WhatsApp on your phone.</li>
              <li>Tap <strong>Menu / Settings</strong> → <strong>Linked devices</strong>.</li>
              <li>Tap <strong>Link a device</strong> and scan this code.</li>
            </ol>
            <div className="wa-qr__frame">
              {qr ? (
                <img src={qr} alt="WhatsApp login QR code" />
              ) : (
                <div className="wa-qr__placeholder">
                  {loading ? 'Loading QR code…' : 'Waiting for QR code…'}
                </div>
              )}
            </div>
            <div className="wa-qr__hint">
              The code refreshes automatically. Keep this open until it links.
            </div>
          </>
        )}

        <div className="wa-qr__actions">
          <button type="button" className="btn btn-outline-secondary btn-sm" onClick={onClose}>
            {loggedIn ? 'Close' : 'Cancel'}
          </button>
        </div>
      </div>
    </div>
  )
}
