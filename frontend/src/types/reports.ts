// Reports module types (ported from the legacy WinForms Reports).

export interface ReportColumn {
  key: string
  label: string
  align: 'left' | 'right' | 'center'
  format: 'money' | 'int' | 'date' | null
}

export interface ReportDef {
  key: string
  label: string
  group: string
  needs_date_range?: boolean
  needs_dwell_days?: boolean
  needs_supplier?: boolean
  needs_division?: boolean
}

export interface ReportResult {
  report: string
  title: string
  columns: ReportColumn[]
  rows: Record<string, unknown>[]
  summary: Record<string, unknown> | null
}

export interface SupplierOption {
  supplier_code: string
  supplier_name: string | null
}

/** Parameters that drive a report run (all optional beyond tenant/store). */
export interface ReportParams {
  from?: string
  to?: string
  dwell_days?: number
  supplier_code?: string
  division_code?: string
}
