/** Types for the Time Report module (COSEC attendance). Mirrors the JSON
 *  shapes returned by backend/modules/time_report. */

export interface ReportInfo {
  key: string
  label: string
  group: string
  description: string
}

export interface DepartmentOption {
  DPTID: number
  Name: string | null
}

export interface UserOption {
  UserID: string
  Name: string | null
  DPTID: number | null
}

export interface DateBounds {
  min: string
  max: string
}

export interface TimeReportMeta {
  reports: ReportInfo[]
  departments: DepartmentOption[]
  users: UserOption[]
  bounds: DateBounds
  today: string
  this_year: number
  this_month: number
}

export interface LegendItem {
  label: string
  hex: string
  code: string
}

export interface Totals {
  full: number
  short: number
  low: number
  miss_punch: number
  absent: number
  late: number
  present: number
}

/** One classified attendance day (daily rows, miss-punch rows, user detail). */
export interface DayRecord {
  user_id: string
  name: string
  department: string
  dpt_id: number | null
  punches: string[]
  punch_count: number
  first_in: string
  last_out: string
  work_minutes: number
  work_hm: string
  late_in: number
  early_out: number
  is_late: boolean
  status: string
  status_label: string
  status_hex: string
  status_text: string
  status_code: string
  pdate_str?: string
}

export interface DailyDept {
  name: string
  dpt_id: number | null
  rows: DayRecord[]
  totals: Totals
}

export interface DailyReport {
  title: string
  date: string
  date_fmt: string
  period: string
  departments: DailyDept[]
  totals: Totals
  legend: LegendItem[]
}

export interface MonthlyCell {
  code: string
  status: string | null
  hex: string
  work_hm: string
}

export interface MonthlyRow {
  user_id: string
  name: string
  dpt_id: number | null
  department: string
  cells: MonthlyCell[]
  present: number
  absent: number
  miss_punch: number
  late: number
  total_hm: string
}

export interface MonthlyReport {
  title: string
  year: number
  month: number
  month_name: string
  days_in_month: number
  days: number[]
  rows: MonthlyRow[]
  totals: Totals
  legend: LegendItem[]
}

export interface MissPunchReport {
  title: string
  start: string
  end: string
  rows: DayRecord[]
  count: number
  legend: LegendItem[]
}

export interface UserSummaryRow {
  user_id: string
  name: string
  department: string
  present: number
  full: number
  short: number
  low: number
  miss_punch: number
  absent: number
  late: number
  total_hm: string
}

export interface UserReport {
  title: string
  start: string
  end: string
  mode: 'detail' | 'summary'
  rows: DayRecord[] | UserSummaryRow[]
  legend: LegendItem[]
  search: string
}

export interface InactiveRow {
  user_id: string
  name: string
  department: string
  join_dt: string
  last_seen: string
  days_since: number | string
}

export interface InactiveReport {
  title: string
  inactive_days: number
  rows: InactiveRow[]
  count: number
}

export interface TimeReportParams {
  date?: string
  year?: number
  month?: number
  dept_id?: string
  user_id?: string
  start?: string
  end?: string
  mode?: string
  search?: string
  days?: number
}
