const SECRET_KEY = /token|password|secret|pin|authorization|credential|api[_-]?key/i;

function isScalar(value) {
  return value == null || ['string', 'number', 'boolean'].includes(typeof value);
}

function cellText(value) {
  if (value == null) return '';
  if (Array.isArray(value)) return value.map((item) => (isScalar(item) ? String(item ?? '') : '')).filter(Boolean).join(', ');
  if (!isScalar(value)) return '';
  return value;
}

export function extractRows(payload) {
  if (Array.isArray(payload)) return payload.filter((row) => row && typeof row === 'object' && !Array.isArray(row));
  if (!payload || typeof payload !== 'object') return [];
  if (Array.isArray(payload.stores) && payload.stores.some((store) => Array.isArray(store?.products))) {
    return payload.stores.flatMap((store) => (store.products || []).map((product) => ({
      store: store.store_name || store.store_code || store.name || store.store_id || '',
      ...product,
    })));
  }
  const preferred = ['items', 'rows', 'suppliers', 'products', 'stores', 'cycles', 'bills', 'orders', 'users', 'results', 'mappings', 'rules', 'reports'];
  for (const key of preferred) {
    if (Array.isArray(payload[key])) {
      return payload[key].filter((row) => row && typeof row === 'object');
    }
  }
  for (const value of Object.values(payload)) {
    if (Array.isArray(value) && value.some((row) => row && typeof row === 'object' && !Array.isArray(row))) {
      return value.filter((row) => row && typeof row === 'object' && !Array.isArray(row));
    }
  }
  const scalars = {};
  let any = false;
  Object.entries(payload).forEach(([key, value]) => {
    if (SECRET_KEY.test(key)) return;
    if (isScalar(value)) {
      scalars[key] = value;
      any = true;
    }
  });
  return any ? [scalars] : [];
}

export function presentTable(payload, { columnLimit = 8 } = {}) {
  const rows = extractRows(payload);
  const declared = Array.isArray(payload?.columns)
    ? payload.columns.filter((column) => column && column.key && !SECRET_KEY.test(column.key))
    : [];
  if (declared.length && rows.length) {
    const columns = declared.slice(0, columnLimit).map((column) => ({
      key: column.key,
      label: column.label || column.key,
    }));
    return {
      columns,
      rows: rows.map((row) => {
        const flat = {};
        columns.forEach((column) => {
          flat[column.key] = cellText(row[column.key]);
        });
        return flat;
      }),
    };
  }
  const keys = [];
  rows.slice(0, 25).forEach((row) => {
    Object.keys(row || {}).forEach((key) => {
      if (SECRET_KEY.test(key) || keys.includes(key)) return;
      const value = row[key];
      if (value != null && typeof value === 'object' && !Array.isArray(value)) return;
      keys.push(key);
    });
  });
  const columns = keys.slice(0, columnLimit).map((key) => ({
    key,
    label: key.replace(/_/g, ' '),
  }));
  return {
    columns,
    rows: rows.map((row) => {
      const flat = {};
      columns.forEach((column) => {
        flat[column.key] = cellText(row[column.key]);
      });
      return flat;
    }),
  };
}
