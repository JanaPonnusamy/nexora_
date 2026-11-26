import fs from 'node:fs';
import path from 'node:path';

const appPath = path.resolve('E:/Nexora/desktop/supplier-stock-client/src/App.jsx');
const cssPath = path.resolve('E:/Nexora/desktop/supplier-stock-client/src/styles.css');
const outJsx = path.resolve('E:/Nexora/desktop/nextech-mediq/src/modules/stock-enquiry/storeClientStockEnquiry.jsx');
const outCss = path.resolve('E:/Nexora/desktop/nextech-mediq/src/modules/stock-enquiry/storeClientStockEnquiry.css');

const lines = fs.readFileSync(appPath, 'utf8').split(/\r?\n/);
const slice = (start, end) => lines.slice(start - 1, end).join('\n');

const header = `import { Fragment, useEffect, useMemo, useRef, useState } from 'react';
import { apiGet, apiPost } from '../../api/client.js';
import { listStores as directoryListStores } from '../../services/directoryService.js';
import {
  syncStoreIndex,
  upsertProducts,
  loadScope,
  filterProducts,
  getLastSync,
} from '../../../../supplier-stock-client/src/lib/productIndexCache.js';
import {
  applySyncResult,
  buildSynchronizedMap,
  emptySelectionState,
  selectionFor as selectionForStore,
  selectionStateForClick,
} from '../../../../supplier-stock-client/src/state/productSelection.js';
import './storeClientStockEnquiry.css';

// Verbatim Store Client Stock Enquiry (desktop/supplier-stock-client/src/App.jsx
// StockVerticalView + StoreComparisonMatrix). The only adaptation is the api
// object below, which calls this app's authenticated client with the workspace
// tenant. Search, matching, and calculations are unchanged.

let boundTenantId = '';

export function bindStockEnquiryTenant(tenantId) {
  boundTenantId = tenantId || '';
}

function tenantOf(filters) {
  return filters?.tenantId || boundTenantId;
}

function asArray(value) {
  if (Array.isArray(value)) return value;
  if (Array.isArray(value?.items)) return value.items;
  if (Array.isArray(value?.data)) return value.data;
  return [];
}

const api = {
  listStores() {
    return directoryListStores();
  },
  getProductIndex(_session, filters = {}) {
    const params = new URLSearchParams({ tenant_id: tenantOf(filters) });
    if (filters.storeId) params.set('store_id', filters.storeId);
    return apiGet(\`/api/stock-availability/products/index?\${params.toString()}\`);
  },
  searchStockProducts(query, _session, filters = {}) {
    const params = new URLSearchParams({
      tenant_id: tenantOf(filters),
      q: query,
      only_stock: filters.onlyStock ? '1' : '0',
    });
    return apiGet(\`/api/stock-availability/products/search?\${params.toString()}\`);
  },
  searchStockBatches(query, _session, filters = {}) {
    const params = new URLSearchParams({
      tenant_id: tenantOf(filters),
      batch: query?.batch || '',
      mrp: query?.mrp || '',
      product: query?.product || '',
    });
    return apiGet(\`/api/stock-availability/batches/search?\${params.toString()}\`);
  },
  getStockCore(storeId, productCode, _session, filters = {}) {
    const params = new URLSearchParams({
      tenant_id: tenantOf(filters),
      store_id: storeId,
      product: productCode,
      months: String(filters.months || 3),
    });
    return apiGet(\`/api/stock-availability/products/core?\${params.toString()}\`);
  },
  syncStockSelection(sourceStoreId, sourceProductCode, sourceProductName, targetStoreIds, _session, filters = {}) {
    return apiPost('/api/stock-availability/products/sync-selection', {
      tenant_id: tenantOf(filters),
      source_store_id: sourceStoreId,
      source_product_code: sourceProductCode,
      source_product_name: sourceProductName,
      target_store_ids: targetStoreIds || [],
    });
  },
  getBillItems(storeId, billNo, billDate, _session, filters = {}) {
    const params = new URLSearchParams({
      tenant_id: tenantOf(filters),
      store_id: storeId,
      bill_no: billNo,
    });
    if (billDate) params.set('bill_date', String(billDate).slice(0, 10));
    return apiGet(\`/api/stock-availability/products/bill?\${params.toString()}\`);
  },
};

const DEFAULT_STOCK_FIELDS = {
  trend: { purchase: true, sales: true, stock: true },
};
`;

let body = [
  slice(132, 155),
  slice(162, 173),
  slice(228, 279),
  slice(843, 848),
  slice(5254, 5254),
  slice(5747, 5842),
  slice(5926, 6001),
  slice(6106, 6112),
  slice(6279, 6287),
  slice(6430, 6679),
  slice(6685, 6690),
  slice(7334, 7340),
  slice(9786, 10566),
  slice(10811, 10820),
].join('\n\n');

body = body.replace(
  'function StockVerticalView({ session, settings, compact = false }) {',
  'export function StockVerticalView({ session, settings, compact = false, embedded = false }) {',
);

body = body.replace(
  '<section className="screen-panel sv-screen">\n      <ScreenHeader title={compact ? \'Quick Stock\' : \'Stock Enquiry\'} />',
  '<section className="screen-panel sv-screen">\n      {embedded ? null : <ScreenHeader title={compact ? \'Quick Stock\' : \'Stock Enquiry\'} />}',
);

fs.writeFileSync(outJsx, `${header}\n${body}\n`);

function prefixCss(css, scope) {
  function walk(source) {
    let i = 0;
    let chunk = '';
    const skipWs = () => {
      while (i < source.length && /\s/.test(source[i])) i += 1;
    };
    const readUntilBrace = () => {
      const start = i;
      while (i < source.length && source[i] !== '{') i += 1;
      return source.slice(start, i);
    };
    const readBlock = () => {
      let depth = 0;
      const start = i;
      while (i < source.length) {
        if (source[i] === '{') depth += 1;
        else if (source[i] === '}') {
          depth -= 1;
          if (depth === 0) {
            i += 1;
            return source.slice(start, i);
          }
        }
        i += 1;
      }
      return source.slice(start);
    };
    const prefixSelectorList = (selectorText) => selectorText
      .split(',')
      .map((part) => {
        const sel = part.trim();
        if (!sel) return '';
        if (sel.startsWith('@')) return sel;
        if (sel.startsWith(':root')) {
          const rest = sel.replace(/^:root(\[[^\]]+\])?/, '').trim();
          const theme = /data-theme="dark"/.test(sel) ? '[data-bs-theme="dark"] ' : '';
          return `${theme}${scope}${rest ? ` ${rest}` : ''}`;
        }
        return `${scope} ${sel}`;
      })
      .filter(Boolean)
      .join(',\n');

    while (i < source.length) {
      skipWs();
      if (i >= source.length) break;
      const selector = readUntilBrace().trim();
      if (!selector || source[i] !== '{') break;
      const block = readBlock();
      const inner = block.slice(1, -1);
      if (selector.startsWith('@media') || selector.startsWith('@supports')) {
        chunk += `${selector} {\n${walk(inner)}\n}\n`;
      } else if (selector.startsWith('@')) {
        chunk += `${selector} ${block}\n`;
      } else {
        chunk += `${prefixSelectorList(selector)} ${block}\n`;
      }
    }
    return chunk;
  }
  return walk(css.replace(/\/\*[\s\S]*?\*\//g, ''));
}

const cssLines = fs.readFileSync(cssPath, 'utf8').split(/\r?\n/);
const cssSlice = (start, end) => cssLines.slice(start - 1, end).join('\n');
const rawCss = [
  cssSlice(405, 425),
  cssSlice(3019, 3180),
  cssSlice(3261, 3700),
  cssSlice(5817, 5836),
  cssSlice(6192, 6226),
  cssSlice(9882, 10174),
].join('\n\n');

const scoped = `/* Store Client Stock Enquiry styles, scoped so they do not restyle other modules.
   Source: desktop/supplier-stock-client/src/styles.css (sv/scm/sa-chart/bill cards). */
.ntm-store-stock {
  flex: 1 1 auto;
  min-height: 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  --nx-radius: 8px;
  --nx-radius-sm: 6px;
  --nx-accent-on: var(--nx-text-on, #ffffff);
  --nx-shadow-sm: var(--ntm-shadow);
}
.ntm-store-stock > .sv-screen {
  flex: 1 1 auto;
  min-height: 0;
  width: 100%;
}

${prefixCss(rawCss, '.ntm-store-stock')}
`;

fs.writeFileSync(outCss, scoped);
console.log('jsx bytes', fs.statSync(outJsx).size, 'css bytes', fs.statSync(outCss).size);
