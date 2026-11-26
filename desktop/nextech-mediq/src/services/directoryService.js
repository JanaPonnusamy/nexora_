// Existing directory endpoints. Both are GET and already scoped by the
// server: a non-broad user receives only their own tenant and that
// tenant's stores (backend/controllers/tenant_controller.py,
// backend/controllers/store_controller.py). Inactive rows are hidden
// in the client the same way supplier-stock-client hides them.
import { apiGet } from '../api/client.js';

function activeRows(rows) {
  return Array.isArray(rows) ? rows.filter((row) => row && row.is_active !== false) : [];
}

export function listTenants() {
  return apiGet('/api/tenants').then(activeRows);
}

export function listStores() {
  return apiGet('/api/stores').then(activeRows);
}
