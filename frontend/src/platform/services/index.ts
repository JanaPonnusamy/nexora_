// Platform Services layer: the only place business-module code should touch
// anything Electron-adjacent (dialogs, clipboard, settings storage) or
// cross-cutting (session, logging, notifications). A module never imports
// `window.uninex`, `navigator.clipboard`, or `localStorage` directly.
export { dialogService } from './DialogService'
export type { ConfirmOptions } from './DialogService'
export { settingsService } from './SettingsService'
export { clipboardService } from './ClipboardService'

// Re-exported here so "platform services" has one import path, even though
// these live in their own folders for historical/organizational reasons
// (built in earlier phases before this layer was named).
export { useSession, getSessionSnapshot, withSessionDefaults } from '../session/SessionContext'
export type { Session } from '../session/SessionContext'
export { logger } from '../logging/Logger'
export { notify, notificationService } from '../ui/notificationService'
export { errorService } from '../errors/ErrorService'

// FileService, PrintService, and UpdateService are deliberately not built
// yet — no module needs them today, and stubbing them out would just be
// unused code. When a module needs one, add it here following the same
// pattern (a thin object wrapping the relevant browser/Electron API, with
// module code never reaching past this layer).
