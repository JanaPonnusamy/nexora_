import React from 'react';
import { useLocation } from 'react-router-dom';
import { PageLayout } from '../../layouts/PageLayout.jsx';
import { EmptyState } from '../../components/states/EmptyState.jsx';
import { findNavItemByPath, statusLabel } from '../../navigation/navConfig.js';

export function PlannedModulePage() {
  const { pathname } = useLocation();
  const item = findNavItemByPath(pathname);

  return (
    <PageLayout title={item?.label || 'Unavailable module'}>
      <EmptyState
        title={`${item?.label || 'Module'} is ${statusLabel(item?.status).toLowerCase()}`}
        description="This is a reserved navigation destination. It is not a working module and will not call the backend until a later phase implements it against an existing API."
      />
    </PageLayout>
  );
}
