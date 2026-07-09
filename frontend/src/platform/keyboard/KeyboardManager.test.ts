import { beforeEach, describe, expect, it, vi } from 'vitest'
import { keyboardManager } from './KeyboardManager'

// A plain object matching the handful of properties KeyboardManager reads —
// avoids depending on the real DOM KeyboardEvent constructor, which isn't
// available under vitest's plain 'node' test environment.
function keydown(init: {
  key: string
  ctrlKey?: boolean
  shiftKey?: boolean
  altKey?: boolean
  metaKey?: boolean
}): KeyboardEvent {
  return {
    key: init.key,
    ctrlKey: init.ctrlKey ?? false,
    shiftKey: init.shiftKey ?? false,
    altKey: init.altKey ?? false,
    metaKey: init.metaKey ?? false,
  } as KeyboardEvent
}

describe('KeyboardManager', () => {
  beforeEach(() => {
    keyboardManager.clear()
  })

  it('invokes the registered handler for a matching combo', () => {
    const handler = vi.fn()
    keyboardManager.register('ctrl+s', handler)

    const handled = keyboardManager.handle(keydown({ key: 's', ctrlKey: true }))

    expect(handled).toBe(true)
    expect(handler).toHaveBeenCalledTimes(1)
  })

  it('returns false and calls nothing for an unregistered combo', () => {
    const handled = keyboardManager.handle(keydown({ key: 'z', ctrlKey: true }))
    expect(handled).toBe(false)
  })

  it('distinguishes modifier combinations (ctrl+f vs ctrl+shift+f)', () => {
    const plain = vi.fn()
    const shifted = vi.fn()
    keyboardManager.register('ctrl+f', plain)
    keyboardManager.register('ctrl+shift+f', shifted)

    keyboardManager.handle(keydown({ key: 'f', ctrlKey: true }))
    keyboardManager.handle(keydown({ key: 'f', ctrlKey: true, shiftKey: true }))

    expect(plain).toHaveBeenCalledTimes(1)
    expect(shifted).toHaveBeenCalledTimes(1)
  })

  it('supports the full required shortcut set (Ctrl+S/F/N/P, F2, F5, Esc, Enter) without conflict', () => {
    const combos = ['ctrl+s', 'ctrl+f', 'ctrl+n', 'ctrl+p', 'f2', 'f5', 'escape', 'enter']
    for (const combo of combos) {
      expect(() => keyboardManager.register(combo, () => {})).not.toThrow()
    }
    for (const combo of combos) {
      expect(keyboardManager.isRegistered(combo)).toBe(true)
    }
  })

  it('registering an already-registered combo throws — this is the conflict guard modules rely on', () => {
    keyboardManager.register('ctrl+s', () => {})
    expect(() => keyboardManager.register('ctrl+s', () => {})).toThrow(/already registered/)
  })

  it('the unsubscribe function returned by register() frees the combo for re-registration', () => {
    const unregister = keyboardManager.register('ctrl+n', () => {})
    unregister()
    expect(keyboardManager.isRegistered('ctrl+n')).toBe(false)
    expect(() => keyboardManager.register('ctrl+n', () => {})).not.toThrow()
  })

  it('a module unregistering its own shortcut does not affect another module’s shortcut (no cross-module coupling)', () => {
    const moduleAHandler = vi.fn()
    const moduleBHandler = vi.fn()
    const unregisterA = keyboardManager.register('ctrl+s', moduleAHandler)
    keyboardManager.register('ctrl+p', moduleBHandler)

    unregisterA()
    keyboardManager.handle(keydown({ key: 'p', ctrlKey: true }))

    expect(moduleAHandler).not.toHaveBeenCalled()
    expect(moduleBHandler).toHaveBeenCalledTimes(1)
    expect(keyboardManager.isRegistered('ctrl+p')).toBe(true)
  })

  it('survives many register/unregister cycles with zero leaked shortcuts', () => {
    for (let i = 0; i < 500; i++) {
      const unregister = keyboardManager.register('f2', () => {})
      unregister()
    }
    expect(keyboardManager.isRegistered('f2')).toBe(false)
  })
})
