import { describe, expect, it, vi } from 'vitest'
import { ModuleLifecycleController } from './ModuleLifecycleController'
import type { ModuleDefinition } from './types'

function makeDefinition(calls: string[]): ModuleDefinition {
  return {
    id: 'reports',
    title: 'Reports',
    nav: { id: 'reports', label: 'Reports', group: 'Test', path: '/reports' },
    component: vi.fn() as unknown as ModuleDefinition['component'],
    lifecycle: {
      initialize: () => void calls.push('initialize'),
      load: () => void calls.push('load'),
      activate: () => void calls.push('activate'),
      deactivate: () => void calls.push('deactivate'),
      saveState: () => void calls.push('saveState'),
      restoreState: () => void calls.push('restoreState'),
      dispose: () => void calls.push('dispose'),
    },
  }
}

describe('ModuleLifecycleController', () => {
  it('mount() calls initialize -> load -> activate in order', async () => {
    const calls: string[] = []
    const controller = new ModuleLifecycleController(makeDefinition(calls))

    await controller.mount()

    expect(calls).toEqual(['initialize', 'load', 'activate'])
    expect(controller.getState()).toBe('active')
  })

  it('deactivate() calls deactivate -> saveState and only from active state', async () => {
    const calls: string[] = []
    const controller = new ModuleLifecycleController(makeDefinition(calls))
    await controller.mount()
    calls.length = 0

    await controller.deactivate()
    expect(calls).toEqual(['deactivate', 'saveState'])
    expect(controller.getState()).toBe('inactive')

    // Calling again while already inactive is a no-op, not a repeat call.
    await controller.deactivate()
    expect(calls).toEqual(['deactivate', 'saveState'])
  })

  it('reactivate() calls restoreState -> activate', async () => {
    const calls: string[] = []
    const controller = new ModuleLifecycleController(makeDefinition(calls))
    await controller.mount()
    await controller.deactivate()
    calls.length = 0

    await controller.reactivate()
    expect(calls).toEqual(['restoreState', 'activate'])
    expect(controller.getState()).toBe('active')
  })

  it('unmount() from active state deactivates, saves, then disposes', async () => {
    const calls: string[] = []
    const controller = new ModuleLifecycleController(makeDefinition(calls))
    await controller.mount()
    calls.length = 0

    await controller.unmount()
    expect(calls).toEqual(['deactivate', 'saveState', 'dispose'])
    expect(controller.getState()).toBe('disposed')
  })

  it('unmount() from inactive state skips deactivate/saveState and only disposes', async () => {
    const calls: string[] = []
    const controller = new ModuleLifecycleController(makeDefinition(calls))
    await controller.mount()
    await controller.deactivate()
    calls.length = 0

    await controller.unmount()
    expect(calls).toEqual(['dispose'])
  })

  it('mount() throws if called twice', async () => {
    const controller = new ModuleLifecycleController(makeDefinition([]))
    await controller.mount()
    await expect(controller.mount()).rejects.toThrow(/already mounted/)
  })

  it('works when a module implements no lifecycle hooks at all', async () => {
    const definition: ModuleDefinition = {
      id: 'bare',
      title: 'Bare',
      nav: { id: 'bare', label: 'Bare', group: 'Test', path: '/bare' },
      component: vi.fn() as unknown as ModuleDefinition['component'],
    }
    const controller = new ModuleLifecycleController(definition)
    await expect(controller.mount()).resolves.toBeUndefined()
    await expect(controller.unmount()).resolves.toBeUndefined()
  })
})
