// Quick Stock -- fast cross-store product lookup for the counter.
// Reuses StockMatrixView (Store Grid / Chart / Batch / Purchase / Sales
// bands with bill & GRN drawers), the same authenticated matrix already
// proven under Stock Enquiry's "Stock Vertical" tab, instead of the old
// kiosk-mode passcode stub (owner: "remove this and wire this module here").
// Unlike the standalone frontend/src/pages/quick-stock kiosk page this is
// ported from, there is no separate PIN gate here -- the desktop app's own
// login session and header tenant/store already authorize this screen
// (owner decision 2026-11-14: reuse app session, not a kiosk passcode).
import React from 'react';
import { PageLayout } from '../../layouts/PageLayout.jsx';
import { StockMatrixView } from './StockMatrixView.jsx';

export function QuickStockPage() {
  return (
    <PageLayout title="Quick Stock" dense>
      <StockMatrixView title="Cross-store lookup" />
    </PageLayout>
  );
}
