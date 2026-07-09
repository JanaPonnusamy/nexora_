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

  /** Diagnostic hook for leak-hunting (e.g. a stress test asserting a count returns to 0 after N subscribe/unsubscribe cycles). */
  listenerCount<K extends keyof EventMap>(event: K): number {
    return this.handlers.get(event)?.size ?? 0
  }
}

// App-wide event map. Deliberately contains ONLY the two events the
// platform itself owns (emitted by ModuleHost) — business event names
// ('purchase.saved', 'export.finished', ...) do not belong in platform
// code, or every new module would require editing this shared file.
// Instead, a module augments this interface via TypeScript declaration
// merging in its own file:
//
//   declare module '../../platform/events/EventBus' {
//     interface PlatformEventMap {
//       'purchase.saved': { cycleId: string }
//     }
//   }
//
// That keeps typed events discoverable (still one interface, just merged
// across files) without coupling this file to any module's vocabulary.
export interface PlatformEventMap {
  'module.activated': { moduleId: string }
  'module.deactivated': { moduleId: string }
  [event: string]: unknown
}

export const eventBus = new EventBus<PlatformEventMap>()
