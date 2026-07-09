import { describe, expect, it, vi } from 'vitest'
import { EventBus, type PlatformEventMap } from './EventBus'

describe('EventBus', () => {
  it('delivers emitted payloads to subscribed handlers', () => {
    const bus = new EventBus<PlatformEventMap>()
    const handler = vi.fn()
    bus.on('purchase.saved', handler)

    bus.emit('purchase.saved', { cycleId: 'cycle-1' })

    expect(handler).toHaveBeenCalledWith({ cycleId: 'cycle-1' })
  })

  it('supports multiple handlers on the same event', () => {
    const bus = new EventBus<PlatformEventMap>()
    const a = vi.fn()
    const b = vi.fn()
    bus.on('refresh.completed', a)
    bus.on('refresh.completed', b)

    bus.emit('refresh.completed', { cycleId: 'cycle-1' })

    expect(a).toHaveBeenCalledTimes(1)
    expect(b).toHaveBeenCalledTimes(1)
  })

  it('on() returns an unsubscribe function', () => {
    const bus = new EventBus<PlatformEventMap>()
    const handler = vi.fn()
    const unsubscribe = bus.on('export.finished', handler)

    unsubscribe()
    bus.emit('export.finished', { cycleId: 'cycle-1' })

    expect(handler).not.toHaveBeenCalled()
  })

  it('off() stops a specific handler without affecting others', () => {
    const bus = new EventBus<PlatformEventMap>()
    const a = vi.fn()
    const b = vi.fn()
    bus.on('inventory.updated', a)
    bus.on('inventory.updated', b)

    bus.off('inventory.updated', a)
    bus.emit('inventory.updated', { storeId: 'store-1' })

    expect(a).not.toHaveBeenCalled()
    expect(b).toHaveBeenCalledTimes(1)
  })

  it('emitting an event with no subscribers does not throw', () => {
    const bus = new EventBus<PlatformEventMap>()
    expect(() => bus.emit('module.activated', { moduleId: 'reports' })).not.toThrow()
  })

  it('clear() removes all subscriptions', () => {
    const bus = new EventBus<PlatformEventMap>()
    const handler = vi.fn()
    bus.on('module.deactivated', handler)

    bus.clear()
    bus.emit('module.deactivated', { moduleId: 'reports' })

    expect(handler).not.toHaveBeenCalled()
  })

  it('registering the same handler reference twice does not duplicate delivery', () => {
    const bus = new EventBus<PlatformEventMap>()
    const handler = vi.fn()
    bus.on('module.activated', handler)
    bus.on('module.activated', handler)

    bus.emit('module.activated', { moduleId: 'reports' })

    expect(handler).toHaveBeenCalledTimes(1)
    expect(bus.listenerCount('module.activated')).toBe(1)
  })

  it('leaves zero listeners after many subscribe/unsubscribe cycles (no leak)', () => {
    const bus = new EventBus<PlatformEventMap>()
    for (let i = 0; i < 500; i++) {
      const unsubscribe = bus.on('refresh.completed', () => {})
      unsubscribe()
    }
    expect(bus.listenerCount('refresh.completed')).toBe(0)
  })

  it('a module unsubscribing does not affect another module’s subscription to the same event (no cross-module coupling)', () => {
    const bus = new EventBus<PlatformEventMap>()
    const moduleAHandler = vi.fn()
    const moduleBHandler = vi.fn()
    const unsubscribeA = bus.on('inventory.updated', moduleAHandler)
    bus.on('inventory.updated', moduleBHandler)

    unsubscribeA()
    bus.emit('inventory.updated', { storeId: 'store-1' })

    expect(moduleAHandler).not.toHaveBeenCalled()
    expect(moduleBHandler).toHaveBeenCalledTimes(1)
    expect(bus.listenerCount('inventory.updated')).toBe(1)
  })
})
