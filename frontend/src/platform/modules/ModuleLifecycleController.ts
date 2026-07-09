import type { ModuleContext, ModuleDefinition } from './types'

export type ModuleLifecycleState = 'idle' | 'active' | 'inactive' | 'disposed'

// Drives one module instance through the fixed lifecycle order the platform
// spec defines: Initialize -> Load -> Activate on mount, Deactivate ->
// SaveState when the module's tab loses focus, RestoreState -> Activate when
// it regains it, and Deactivate -> SaveState -> Dispose on close. Calls only
// the hooks a given module actually implements; out-of-order calls (e.g.
// deactivating an already-inactive module) are no-ops rather than errors so
// callers don't need to track state themselves.
export class ModuleLifecycleController {
  readonly moduleId: string
  private readonly definition: ModuleDefinition
  private readonly context: ModuleContext
  private state: ModuleLifecycleState = 'idle'

  constructor(definition: ModuleDefinition, context?: ModuleContext) {
    this.definition = definition
    this.moduleId = definition.id
    this.context = context ?? { moduleId: definition.id }
  }

  getState(): ModuleLifecycleState {
    return this.state
  }

  async mount(): Promise<void> {
    if (this.state !== 'idle') {
      throw new Error(`Module "${this.moduleId}" already mounted (state: ${this.state})`)
    }
    const { lifecycle } = this.definition
    await lifecycle?.initialize?.(this.context)
    await lifecycle?.load?.(this.context)
    await lifecycle?.activate?.(this.context)
    this.state = 'active'
  }

  async deactivate(): Promise<void> {
    if (this.state !== 'active') return
    const { lifecycle } = this.definition
    await lifecycle?.deactivate?.(this.context)
    await lifecycle?.saveState?.(this.context)
    this.state = 'inactive'
  }

  async reactivate(): Promise<void> {
    if (this.state !== 'inactive') return
    const { lifecycle } = this.definition
    await lifecycle?.restoreState?.(this.context)
    await lifecycle?.activate?.(this.context)
    this.state = 'active'
  }

  async unmount(): Promise<void> {
    if (this.state === 'disposed') return
    if (this.state === 'active') {
      const { lifecycle } = this.definition
      await lifecycle?.deactivate?.(this.context)
      await lifecycle?.saveState?.(this.context)
    }
    await this.definition.lifecycle?.dispose?.(this.context)
    this.state = 'disposed'
  }
}
