import { describe, expect, it, vi } from 'vitest'
import { ModuleRegistry } from './ModuleRegistry'
import type { ModuleDefinition } from './types'

function makeModule(id: string): ModuleDefinition {
  return {
    id,
    title: id,
    nav: { id, label: id, group: 'Test', path: `/${id}` },
    component: vi.fn() as unknown as ModuleDefinition['component'],
  }
}

describe('ModuleRegistry', () => {
  it('lists modules in registration order', () => {
    const registry = new ModuleRegistry()
    registry.register(makeModule('reports'))
    registry.register(makeModule('inventory'))
    registry.register(makeModule('purchase-manager'))

    expect(registry.list().map((m) => m.id)).toEqual(['reports', 'inventory', 'purchase-manager'])
  })

  it('rejects registering the same module id twice', () => {
    const registry = new ModuleRegistry()
    registry.register(makeModule('reports'))
    expect(() => registry.register(makeModule('reports'))).toThrow(/already registered/)
  })

  it('unregister removes the module and its ordering entry', () => {
    const registry = new ModuleRegistry()
    registry.register(makeModule('reports'))
    registry.register(makeModule('inventory'))
    registry.unregister('reports')

    expect(registry.has('reports')).toBe(false)
    expect(registry.list().map((m) => m.id)).toEqual(['inventory'])
  })

  it('get returns undefined for an unknown module', () => {
    const registry = new ModuleRegistry()
    expect(registry.get('missing')).toBeUndefined()
  })
})
