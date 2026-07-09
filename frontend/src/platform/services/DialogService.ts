export interface ConfirmOptions {
  title?: string
  message: string
}

/**
 * Single place modules ask the user a yes/no question or show a blocking
 * message — never `window.confirm`/`window.alert` (or, in Electron, the
 * native `dialog` module) called directly from module code. Implemented on
 * top of the browser's built-in dialogs today, which render identically in
 * both a browser tab and Electron's renderer (it's still just Chromium);
 * swapping to OS-native dialogs later (via an IPC channel to Electron's
 * `dialog` module, main-process-only) only requires changing this file.
 */
export const dialogService = {
  confirm(options: ConfirmOptions): boolean {
    const message = options.title ? `${options.title}\n\n${options.message}` : options.message
    return window.confirm(message)
  },
  alert(options: ConfirmOptions): void {
    const message = options.title ? `${options.title}\n\n${options.message}` : options.message
    window.alert(message)
  },
}
