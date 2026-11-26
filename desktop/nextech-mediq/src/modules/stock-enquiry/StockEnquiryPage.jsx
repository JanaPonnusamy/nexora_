import React, { useMemo } from 'react';
import { useAuth } from '../../contexts/AuthContext.jsx';
import { StockVerticalView } from './storeClientStockEnquiry.jsx';

export function StockEnquiryPage() {
  const { user, tenantId } = useAuth();
  const session = useMemo(() => ({ user }), [user]);

  return (
    <section className="ntm-page ntm-page--dense">
      <div className="ntm-page__body">
        <div className="ntm-store-stock">
          <StockVerticalView
            embedded
            title="Stock Enquiry"
            session={session}
            settings={{ tenantId }}
          />
        </div>
      </div>
    </section>
  );
}
