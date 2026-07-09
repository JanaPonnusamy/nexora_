import type { ModuleDefinition, ModuleId } from './types'

// Static, compile-time registry — modules register themselves once at app
// startup. No dynamic/hot-loadable plugin loading: the known module set
// (Purchase Manager, Inventory, Sales, Reports, ...) is small and fixed, so a
// plugin system would be unused complexity.
export class ModuleRegistry {
  private modules = new Map<ModuleId, ModuleDefinition>()
  private order: ModuleId[] = []

  register(definition: ModuleDefinition): void {
    if (this.modules.has(definition.id)) {
      throw new Error(`Module "${definition.id}" is already registered`)
    }
    this.modules.set(definition.id, definition)
    this.order.push(definition.id)
  }

  unregister(id: ModuleId): void {
    this.modules.delete(id)
    this.order = this.order.filter((existing) => existing !== id)
  }

  get(id: ModuleId): ModuleDefinition | undefined {
    return this.modules.get(id)
  }

  has(id: ModuleId): boolean {
    return this.modules.has(id)
  }

  /** Registered modules, in registration order. */
  list(): ModuleDefinition[] {
    return this.order.map((id) => this.modules.get(id)!)
  }

  clear(): void {
    this.modules.clear()
    this.order = []
  }
}

// One shared registry for the whole app. Real modules call
// moduleRegistry.register(...) as they're wrapped in the framework (starting
// with Reports as the Phase 2.4 proof-of-concept).
export const moduleRegistry = new ModuleRegistry()
