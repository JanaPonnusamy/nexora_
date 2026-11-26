// Thin routing wrapper around the ported ProcurementWorkspace.jsx (see that
// file's own header for what was and wasn't changed in the port). The real
// screen renders its own full-height <section>, not PageLayout's chrome —
// matching supplier-stock-client's own App.jsx, which rendered it directly
// rather than inside a page shell. This wrapper's only job is supplying the
// `settings` shape the component expects (tenantId/storeId/storeName, the
// same three fields App.jsx's runtimeSettings provided) from this app's own
// useAuth(), and `hidden={false}` — this app unmounts the page on navigation
// instead of the source's CSS-hidden-but-mounted persistence trick, since
// each page here is only rendered while routed to.
import React from 'react';
import { useAuth } from '../../contexts/AuthContext.jsx';
import ProcurementWorkspace from './ProcurementWorkspace.jsx';
import './procurementWorkspace.css';

export function ProcurementWorkspacePage() {
  const { tenantId, storeId, storeName } = useAuth();
  const settings = { tenantId, storeId, storeName };
  return <ProcurementWorkspace settings={settings} hidden={false} />;
}
