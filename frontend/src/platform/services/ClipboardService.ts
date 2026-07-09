/**
 * Single place modules read/write the system clipboard — never
 * `navigator.clipboard` called directly. Works identically in a browser tab
 * and Electron's renderer (both are the same Chromium Clipboard API); an
 * Electron-native `clipboard` module swap (for formats the web API doesn't
 * support, e.g. images) only requires changing this file.
 */
export const clipboardService = {
  async writeText(text: string): Promise<void> {
    await navigator.clipboard.writeText(text)
  },
  async readText(): Promise<string> {
    return navigator.clipboard.readText()
  },
}
