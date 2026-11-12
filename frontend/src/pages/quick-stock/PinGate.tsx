import { useState } from 'react'
import { ApiError } from '../../services/apiClient'
import { pinStorage } from './pinStorage'
import { quickStockService } from './quickStockService'

export function PinGate({ onUnlocked }: { onUnlocked: () => void }) {
  const [pin, setPin] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [checking, setChecking] = useState(false)

  const submit = async () => {
    if (!pin.trim()) return
    setChecking(true)
    setError(null)
    pinStorage.set(pin.trim())
    try {
      await quickStockService.verifyPin(pin.trim())
      onUnlocked()
    } catch (err) {
      pinStorage.clear()
      setError(err instanceof ApiError && err.status === 401 ? 'Wrong passcode' : 'Unable to reach the server')
    } finally {
      setChecking(false)
    }
  }

  return (
    <div className="qs-gate">
      <div className="qs-gate__card">
        <div className="qs-gate__title">Quick Stock</div>
        <div className="qs-gate__sub">Enter the passcode to continue</div>
        <input
          className="qs-gate__input"
          type="password"
          inputMode="numeric"
          autoFocus
          value={pin}
          maxLength={12}
          onChange={(e) => setPin(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && submit()}
          placeholder="••••"
        />
        <button className="qs-gate__btn" disabled={checking || !pin.trim()} onClick={submit}>
          {checking ? 'Checking…' : 'Unlock'}
        </button>
        <div className="qs-gate__error">{error}</div>
      </div>
    </div>
  )
}
