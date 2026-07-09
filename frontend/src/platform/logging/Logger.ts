type LogLevel = 'info' | 'warn' | 'error'

// Forwards to the Electron host's file logger via preload when running
// inside the desktop shell (window.uninex.log); falls back to console when
// running as a plain browser tab, so the same calls work in both hosts.
function write(level: LogLevel, scope: string, message: string, data?: unknown): void {
  const host = typeof window !== 'undefined' ? window.uninex : undefined
  if (host) {
    host.log[level](scope, message, data)
    return
  }
  const line = `[${scope}] ${message}`
  if (level === 'error') console.error(line, data ?? '')
  else if (level === 'warn') console.warn(line, data ?? '')
  else console.info(line, data ?? '')
}

export const logger = {
  info: (scope: string, message: string, data?: unknown) => write('info', scope, message, data),
  warn: (scope: string, message: string, data?: unknown) => write('warn', scope, message, data),
  error: (scope: string, message: string, data?: unknown) => write('error', scope, message, data),
}
