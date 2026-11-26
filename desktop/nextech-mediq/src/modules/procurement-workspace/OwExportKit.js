// Ported verbatim from desktop/supplier-stock-client/src/OwExportKit.js
// (owner instruction: copy logic unchanged, only adapt plumbing/theme).
// No api.* calls in this file to adapt; window.nexoraDesktop references are
// left exactly as in the source — they are only reachable from the Export
// button, which stays disabled in this read-only app (per the owner's rule),
// so this is dead code here, not a functional gap.
import { unzipSync } from 'fflate';
import { offerWhatsAppShare } from './storeWhatsApp.jsx';
import { OW_EXPORT_COLUMN_DEFS } from './OwSharedControls.jsx';

const OW_EXPORT_SETTINGS_FILE = 'order-export-settings.json';
const OW_EXPORT_SETTINGS_LS_KEY = 'nexora.desktop.orderExportSettings';
const OW_EXPORT_DEFAULT_BASE_PATH = 'D:\\Export Order';

export function owDefaultExportSettings() {
  const columns = {};
  OW_EXPORT_COLUMN_DEFS.forEach((c) => { columns[c.key] = true; });
  return {
    basePath: OW_EXPORT_DEFAULT_BASE_PATH,
    fileFormat: 'xls', // 'xls' | 'xlsx' | 'csv'
    columns,
    supplierWise: false,
    images: false
  };
}
export function owMigrateExportSettings(data) {
  let next = data;
  if (next.supplierWise === true && !next._migratedSupplierWiseOff) {
    next = { ...next, supplierWise: false, _migratedSupplierWiseOff: true };
  }
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

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(String(reader.result).split(',')[1] || '');
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

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
export function owSafeFileName(name) {
  return owSafePathSegment(name).replace(/\[/g, '(').replace(/\]/g, ')');
}
export function owSafePathSegment(name) {
  return String(name || '').replace(/[<>:"/\\|?*]/g, '_').replace(/[\x00-\x1f]/g, '').trim() || 'Export';
}
