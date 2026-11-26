// ExcelJS export for the Non-Moving Stock report — same A4-print-ready
// pattern the web frontend uses for Expiry Stock (header fill, frozen header
// row, per-column number/date formats, a bold total row). Client-side only,
// no backend round trip.
import ExcelJS from 'exceljs';

const HEADER_FILL = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFEFEFEF' } };
const TOTAL_FILL = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFF7F2E7' } };
const thin = { style: 'thin', color: { argb: 'FFB0B0B0' } };
const border = { top: thin, left: thin, bottom: thin, right: thin };

function numFmt(fmt) {
  if (fmt === 'money') return '#,##0.00';
  if (fmt === 'int') return '#,##0';
  return undefined;
}

function cellValue(raw, fmt) {
  if (raw === null || raw === undefined || raw === '') return null;
  if (fmt === 'money' || fmt === 'int') {
    const n = Number(raw);
    return Number.isFinite(n) ? n : String(raw);
  }
  if (fmt === 'date') {
    const d = new Date(String(raw));
    return Number.isNaN(d.getTime()) ? String(raw) : d;
  }
  return String(raw);
}

export async function exportNonMovingExcel({ columns, rows, summary, storeName, fileName }) {
  const wb = new ExcelJS.Workbook();
  wb.creator = 'NexTech MediQ';
  wb.created = new Date();

  const ws = wb.addWorksheet('Non-Moving Stock', {
    views: [{ state: 'frozen', ySplit: 2 }],
    pageSetup: {
      paperSize: 9,
      orientation: 'landscape',
      fitToPage: true,
      fitToWidth: 1,
      fitToHeight: 0,
      horizontalCentered: true,
      margins: { left: 0.4, right: 0.4, top: 0.5, bottom: 0.6, header: 0.3, footer: 0.3 },
    },
  });
  ws.pageSetup.printTitlesRow = '2:2';
  ws.headerFooter = {
    oddFooter: '&L&"Calibri,Regular"&9Printed: &D &T&R&"Calibri,Regular"&9Page &P of &N',
    evenFooter: '&L&"Calibri,Regular"&9Printed: &D &T&R&"Calibri,Regular"&9Page &P of &N',
  };

  ws.mergeCells(1, 1, 1, columns.length);
  const title = ws.getCell(1, 1);
  title.value = `Non-Moving Stock${storeName ? ` — ${storeName}` : ''}`;
  title.font = { bold: true, size: 12 };
  title.alignment = { horizontal: 'left', vertical: 'middle' };

  const header = ws.getRow(2);
  columns.forEach((c, i) => {
    const cell = header.getCell(i + 1);
    cell.value = c.label;
    cell.font = { bold: true };
    cell.fill = HEADER_FILL;
    cell.border = border;
    cell.alignment = { horizontal: c.align || 'left', vertical: 'middle', wrapText: true };
  });
  header.height = 20;

  let r = 2;
  for (const row of rows) {
    r += 1;
    const xr = ws.getRow(r);
    columns.forEach((c, i) => {
      const cell = xr.getCell(i + 1);
      cell.value = cellValue(row[c.key], c.format);
      const nf = numFmt(c.format);
      if (nf) cell.numFmt = nf;
      cell.border = border;
      cell.alignment = { horizontal: c.align || 'left', vertical: 'middle' };
    });
  }

  if (summary) {
    r += 1;
    const xr = ws.getRow(r);
    columns.forEach((c, i) => {
      const cell = xr.getCell(i + 1);
      cell.value = cellValue(summary[c.key], c.format);
      const nf = numFmt(c.format);
      if (nf) cell.numFmt = nf;
      cell.font = { bold: true };
      cell.fill = TOTAL_FILL;
      cell.border = border;
      cell.alignment = { horizontal: c.align || 'left', vertical: 'middle' };
    });
  }

  columns.forEach((c, i) => {
    let maxLen = c.label.length;
    for (const row of rows) {
      const v = row[c.key];
      if (v != null) maxLen = Math.max(maxLen, String(v).length);
    }
    ws.getColumn(i + 1).width = Math.min(Math.max(maxLen + 2, 8), 40);
  });

  const buf = await wb.xlsx.writeBuffer();
  const blob = new Blob([buf], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = fileName.endsWith('.xlsx') ? fileName : `${fileName}.xlsx`;
  a.click();
  URL.revokeObjectURL(url);
}
