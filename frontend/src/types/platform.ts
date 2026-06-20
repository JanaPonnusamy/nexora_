export interface KpiMetric {
  key: string
  label: string
  icon: string
  /** Null until the platform statistics endpoint is connected. */
  value: number | null
}

export interface QuickAction {
  label: string
  description: string
  icon: string
  to: string
}

export interface NavigationCardItem {
  label: string
  description: string
  icon: string
  to: string
}
