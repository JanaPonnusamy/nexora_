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

export interface PharmacyCompareStoreRow {
  Store: string
  StoreCode: string
  StoreId: string
  Status: string
  Error?: string
  SalesA: number
  SalesB: number
  SalesGrowthPercent: number
  StockA: number
  StockB: number
  StockGrowthPercent: number
  PendingA: number
  PendingB: number
  PaidUpStockA: number
  PaidUpStockPercentA: number
  PaidUpStockB: number
  PaidUpStockPercentB: number
}

export interface PharmacyCompareResponse {
  success: boolean
  month_a: string
  month_b: string
  stores: PharmacyCompareStoreRow[]
}
