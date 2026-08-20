export type PharmacyReportSource = 'NEXORA' | 'STORE_DB'

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
  Source?: PharmacyReportSource
}

export interface PharmacyDashboardResponse {
  success: boolean
  source: PharmacyReportSource
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
  source: PharmacyReportSource
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
  AvgDailySalesA: number
  AvgDailySalesB: number
  AvgDailySalesGrowthPercent: number
  Source?: PharmacyReportSource
}

export interface PharmacyCompareSummary {
  StoresIncluded: number
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
  AvgDailySalesA: number
  AvgDailySalesB: number
  AvgDailySalesGrowthPercent: number
  WorkingCapitalImpact: number
}

export interface PharmacyCompareResponse {
  success: boolean
  source: PharmacyReportSource
  month_a: string
  month_b: string
  stores: PharmacyCompareStoreRow[]
  summary: PharmacyCompareSummary
  generated_at?: string
}
