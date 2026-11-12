const KEY = 'nexora_quick_stock_pin'

export const pinStorage = {
  get(): string {
    try {
      return localStorage.getItem(KEY) ?? ''
    } catch {
      return ''
    }
  },
  set(pin: string) {
    try {
      localStorage.setItem(KEY, pin)
    } catch {
      // ignore (private browsing / blocked storage) — just asks again next time
    }
  },
  clear() {
    try {
      localStorage.removeItem(KEY)
    } catch {
      // ignore
    }
  },
}
