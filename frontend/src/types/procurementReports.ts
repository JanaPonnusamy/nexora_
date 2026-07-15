export interface PharmacyReportKpi {
  Sales: number
  Purchase: number
  ClosingStock: number
  PendingAmount: number
  PendingInvoices: number
  GP: number
  GPPercent: number
}

export interface PharmacyReportStoreSummary {
  Store: string
  StoreCode: string
  StoreId: string
  Status: string
  Error?: string
  Sales: number
  Purchase: number
  PurchaseReturn: number
  ClosingStock: number
  PendingAmount: number
  PendingInvoices: number
  GP: number
  GPPercent: number
  PurchaseSalesRatio: number
  StockPendingRatio: number
}

export interface PharmacyDashboardResponse {
  success: boolean
  kpi: PharmacyReportKpi
  stores: PharmacyReportStoreSummary[]
}

export interface PharmacyMonthlyRow {
  MonthOfStatistics: string
  Sales: number
  Purchase: number
  PurchaseReturn: number
  OpeningStock: number
  TransferIn: number
  TransferOut: number
  Adjustment: number
  ClosingStock: number
  CostOfSales: number
  PendingAmount: number
  PendingInvoices: number
  GP: number
  GPPercent: number
  PurchaseSalesRatio: number
  StockPendingRatio: number
}

export interface PharmacyStoreAnalysisResponse {
  success: boolean
  store: string
  store_name: string
  store_code: string
  store_id: string
  rows: PharmacyMonthlyRow[]
}
