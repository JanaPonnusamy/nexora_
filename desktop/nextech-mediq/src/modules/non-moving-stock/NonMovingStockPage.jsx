import React from 'react';
import { useAuth } from '../../contexts/AuthContext.jsx';
import NonMovingStock from './NonMovingStock.jsx';
import './nonMovingStock.css';

export function NonMovingStockPage() {
  const { tenantId, storeId, storeName, changeStore } = useAuth();
  const settings = { tenantId, storeId, storeName, onStoreChange: changeStore };
  return <NonMovingStock settings={settings} hidden={false} />;
}
