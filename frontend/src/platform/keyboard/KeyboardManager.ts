export type ShortcutHandler = (event: KeyboardEvent) => void

interface ShortcutEntry {
  combo: string
  handler: ShortcutHandler
}

// Normalizes a KeyboardEvent into the same "ctrl+shift+s" shape used to
// register shortcuts, so lookups are a single Map.get() instead of scanning
// every registration on every keystroke.
function comboFromEvent(event: KeyboardEvent): string {
  const parts: string[] = []
  if (event.ctrlKey || event.metaKey) parts.push('ctrl')
  if (event.shiftKey) parts.push('shift')
  if (event.altKey) parts.push('alt')
  parts.push(event.key.toLowerCase())
  return parts.join('+')
}

/**
 * Global shortcut registry. Platform shell attaches a single document-level
 * keydown listener (see PlatformShell) that consults this registry, instead
 * of every module wiring up its own onKeyDown handler — avoids the shortcut
 * conflicts that ad hoc per-component handlers are prone to.
 */
class KeyboardManager {
  private shortcuts = new Map<string, ShortcutEntry>()

  /** `combo` example: "ctrl+s", "ctrl+shift+f", "f5", "escape". */
  register(combo: string, handler: ShortcutHandler): () => void {
    const key = combo.toLowerCase()
    if (this.shortcuts.has(key)) {
      throw new Error(`Shortcut "${combo}" is already registered`)
    }
    this.shortcuts.set(key, { combo: key, handler })
    return () => this.unregister(combo)
  }

  unregister(combo: string): void {
    this.shortcuts.delete(combo.toLowerCase())
  }

  isRegistered(combo: string): boolean {
    return this.shortcuts.has(combo.toLowerCase())
  }

  /** Returns true if a matching shortcut was found and invoked. */
  handle(event: KeyboardEvent): boolean {
    const entry = this.shortcuts.get(comboFromEvent(event))
    if (!entry) return false
    entry.handler(event)
    return true
  }

  clear(): void {
    this.shortcuts.clear()
  }
}

export const keyboardManager = new KeyboardManager()
