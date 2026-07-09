type EventHandler<T> = (payload: T) => void

// Minimal typed pub/sub so modules can react to each other (e.g. a future
// Dashboard module refreshing its KPIs when Purchase Manager fires
// 'purchase.saved') without importing one another directly. Renderer-only —
// every module runs in the same process, so no IPC/serialization is needed.
export class EventBus<EventMap extends Record<string, unknown>> {
  private handlers = new Map<keyof EventMap, Set<EventHandler<unknown>>>()

  on<K extends keyof EventMap>(event: K, handler: EventHandler<EventMap[K]>): () => void {
    if (!this.handlers.has(event)) this.handlers.set(event, new Set())
    this.handlers.get(event)!.add(handler as EventHandler<unknown>)
    return () => this.off(event, handler)
  }

  off<K extends keyof EventMap>(event: K, handler: EventHandler<EventMap[K]>): void {
    this.handlers.get(event)?.delete(handler as EventHandler<unknown>)
  }

  emit<K extends keyof EventMap>(event: K, payload: EventMap[K]): void {
    this.handlers.get(event)?.forEach((handler) => handler(payload))
  }

  clear(): void {
    this.handlers.clear()
  }
}

// App-wide event map, extended as modules are migrated onto the platform.
// Centralized here (rather than each module inventing its own event names)
// so cross-module wiring stays discoverable in one place.
export interface PlatformEventMap {
  'module.activated': { moduleId: string }
  'module.deactivated': { moduleId: string }
  'purchase.saved': { cycleId: string }
  'inventory.updated': { storeId: string }
  'refresh.completed': { cycleId: string }
  'export.finished': { cycleId: string }
  [event: string]: unknown
}

export const eventBus = new EventBus<PlatformEventMap>()
