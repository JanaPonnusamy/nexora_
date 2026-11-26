import { unzipSync } from 'fflate';
import { offerWhatsAppShare } from './storeWhatsApp.jsx';
import { OW_EXPORT_COLUMN_DEFS } from './OwSharedControls.jsx';

// Order Workspace export settings (destination folder, file format, column
// selection, per-supplier split) and the shared file-write/download helpers
// they use. Extracted from App.jsx (NEXORA MEDIQ Phase 4 structural
// refactor) -- shared by Order Workspace, Procurement (via App.jsx's
// PROCUREMENT_UI.exportKit bridge), the Label Exporter screen and the
// WhatsApp-share path, so it stays its own module rather than living inside
// either OrderWorkspace.jsx or App.jsx exclusively. No behavior changed.

// Persisted once per machine (not per-user like Label Exporter's session,
// since "default export path" is a workstation setting, same spirit as the
// legacy VB.NET app writing to a fixed local folder). Falls back to
// localStorage when the Electron IPC bridge isn't present (e.g. the web
// build), same tolerance pattern as readLabelSession/writeLabelSession.
const OW_EXPORT_SETTINGS_FILE = 'order-export-settings.json';
const OW_EXPORT_SETTINGS_LS_KEY = 'nexora.desktop.orderExportSettings';
const OW_EXPORT_DEFAULT_BASE_PATH = 'D:\\Export Order';

export function owDefaultExportSettings() {
  const columns = {};
  OW_EXPORT_COLUMN_DEFS.forEach((c) => { columns[c.key] = true; });
  return {
    basePath: OW_EXPORT_DEFAULT_BASE_PATH,
    // Owner request (2026-10-22): default to the legacy binary .xls format,
    // not .xlsx -- a downstream consumer specifically needs true BIFF
    // (Excel 97-2003), which openpyxl cannot write; see order_export.py's
    // xlwt-backed _build_workbook_xls/_build_workbook_custom_xls.
    fileFormat: 'xls', // 'xls' | 'xlsx' | 'csv'
    columns,
    // Owner request (2026-10-22): land directly in <basePath>\<ddmmyyyy>\
    // <order no>\file.xls by default, no extra supplier-named subfolder --
    // the checkbox is still available to turn it back on per-install.
    supplierWise: false,
    // Also render the sheet as PNGs, 20 products per image (Part 1, 2, ...).
    images: false
  };
}
// One-time migration (2026-10-22): supplierWise's default flipped true->
// false, but an install that already saved settings has true baked into its
// settings file/localStorage forever -- {...default, ...saved} always lets
// the saved value win, so changing the function above does nothing for an
// existing install. This forces supplierWise to false exactly once (the
// first load after this migration ships), then sets a flag so a user who
// deliberately turns it back ON afterward is respected, not fought forever.
export function owMigrateExportSettings(data) {
  let next = data;
  if (next.supplierWise === true && !next._migratedSupplierWiseOff) {
    next = { ...next, supplierWise: false, _migratedSupplierWiseOff: true };
  }
  // Same one-time-forward-migration pattern for the fileFormat default
  // flip (xlsx -> xls, owner request 2026-10-22): an install that already
  // saved fileFormat:'xlsx' has that baked in forever otherwise.
  if (next.fileFormat === 'xlsx' && !next._migratedFileFormatXls) {
    next = { ...next, fileFormat: 'xls', _migratedFileFormatXls: true };
  }
  return next;
}
export async function readOwExportSettings() {
  try {
    if (window.nexoraDesktop?.readSession) {
      const data = await window.nexoraDesktop.readSession(OW_EXPORT_SETTINGS_FILE);
      if (data && typeof data === 'object') return owMigrateExportSettings({ ...owDefaultExportSettings(), ...data });
    }
  } catch { /* fall through to localStorage */ }
  try {
    const raw = localStorage.getItem(OW_EXPORT_SETTINGS_LS_KEY);
    if (raw) { const p = JSON.parse(raw); if (p && typeof p === 'object') return owMigrateExportSettings({ ...owDefaultExportSettings(), ...p }); }
  } catch { /* ignore corrupt */ }
  return owDefaultExportSettings();
}
export function writeOwExportSettings(data) {
  try { window.nexoraDesktop?.writeSession?.(OW_EXPORT_SETTINGS_FILE, data); } catch { /* ignore */ }
  try { localStorage.setItem(OW_EXPORT_SETTINGS_LS_KEY, JSON.stringify(data)); } catch { /* ignore */ }
}
// ddmmyyyy, matching the legacy app's own folder-date convention.
export function owExportDateFolder(date = new Date()) {
  const dd = String(date.getDate()).padStart(2, '0');
  const mm = String(date.getMonth() + 1).padStart(2, '0');
  const yyyy = String(date.getFullYear());
  return `${dd}${mm}${yyyy}`;
}

export function owDownloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url; link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
  offerWhatsAppShare({ blobs: [{ name: filename, blob }] });
}

// Base64-encodes a Blob for the Electron IPC bridge (ipcRenderer can't pass
// a raw Blob/ArrayBuffer through the structured-clone boundary as cleanly
// as a string), so the main process can Buffer.from(..., 'base64') it
// straight to disk.
function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(String(reader.result).split(',')[1] || '');
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

// Writes an export to <folder>. A split export arrives as a .zip of "Part n of
// m" files -- unpack it so each part lands as its own file in the order folder
// (legacy VB behaviour); otherwise write the single file under `filename`.
// Outside Electron there is no filesystem, so fall back to a browser download.
// `written` (optional) collects every file path actually written.
export async function owSaveExport(blob, backendFilename, filename, folder, written = []) {
  const isZip = /\.zip$/i.test(backendFilename || '');
  const desktop = window.nexoraDesktop?.writeExportFile;
  if (isZip) {
    const parts = unzipSync(new Uint8Array(await blob.arrayBuffer()));
    for (const [name, bytes] of Object.entries(parts)) {
      const partBlob = new Blob([bytes]);
      if (desktop) written.push(await window.nexoraDesktop.writeExportFile(`${folder}\\${name}`, await blobToBase64(partBlob)));
      else owDownloadBlob(partBlob, name);
    }
    return desktop ? folder : null;
  }
  if (desktop) {
    const savedPath = await window.nexoraDesktop.writeExportFile(`${folder}\\${filename}`, await blobToBase64(blob));
    written.push(savedPath);
    return savedPath;
  }
  owDownloadBlob(blob, filename);
  return null;
}
// Strip characters Windows paths can't contain so a supplier/order name
// never breaks the subfolder it's building.
// VB SafeFileName: invalid chars -> '_', and [ ] -> ( ) (Excel-hostile).
export function owSafeFileName(name) {
  return owSafePathSegment(name).replace(/\[/g, '(').replace(/\]/g, ')');
}
export function owSafePathSegment(name) {
  return String(name || '').replace(/[<>:"/\\|?*]/g, '_').replace(/[\x00-\x1f]/g, '').trim() || 'Export';
}
