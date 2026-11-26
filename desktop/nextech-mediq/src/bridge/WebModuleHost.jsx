import React, { Suspense, lazy, useMemo } from 'react';
import { WebAuthBridge } from './webAuthContext.jsx';
import { loadWebPage } from './webPages.js';
import { LoadingState } from '../components/states/LoadingState.jsx';
import { ErrorState } from '../components/states/ErrorState.jsx';
import './webHost.css';

export function WebModuleHost({ pageId }) {
  const load = loadWebPage(pageId);
  const Page = useMemo(() => (load ? lazy(load) : null), [load]);

  if (!Page) {
    return <ErrorState title="Screen missing" message={`No web page is registered for ${pageId}.`} />;
  }

  return (
    <WebAuthBridge>
      <div className="ntm-web-host">
        <Suspense fallback={<LoadingState label="Loading screen" />}>
          <Page />
        </Suspense>
      </div>
    </WebAuthBridge>
  );
}
