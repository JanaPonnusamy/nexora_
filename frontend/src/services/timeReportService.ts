import { api } from './apiClient'
import type {
  DailyReport,
  InactiveReport,
  MissPunchReport,
  MonthlyReport,
  TimeReportMeta,
  TimeReportParams,
  UserReport,
} from '../types/timeReport'

function qs(params: Record<string, string | number | undefined>): string {
  const parts = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== '' && v !== null)
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
  return parts.length ? `?${parts.join('&')}` : ''
}

const clean = (p: TimeReportParams): Record<string, string | number | undefined> => ({ ...p })

export const timeReportService = {
  meta: () => api.get<TimeReportMeta>('/api/time-report/meta'),

  daily: (p: TimeReportParams) =>
    api.get<DailyReport>(`/api/time-report/daily${qs(clean(p))}`),
  monthly: (p: TimeReportParams) =>
    api.get<MonthlyReport>(`/api/time-report/monthly${qs(clean(p))}`),
  misspunch: (p: TimeReportParams) =>
    api.get<MissPunchReport>(`/api/time-report/misspunch${qs(clean(p))}`),
  user: (p: TimeReportParams) =>
    api.get<UserReport>(`/api/time-report/user${qs(clean(p))}`),
  inactive: (p: TimeReportParams) =>
    api.get<InactiveReport>(`/api/time-report/inactive${qs(clean(p))}`),

  /** Path to the styled .xlsx download for a report (fetched as a Blob). */
  exportPath: (report: string, p: TimeReportParams) =>
    `/api/time-report/${report}${qs({ ...clean(p), export: 'xlsx' })}`,

  /** Path to a styled .png of a report (monthly/misspunch/user/inactive). */
  imagePath: (report: string, p: TimeReportParams) =>
    `/api/time-report/${report}${qs({ ...clean(p), export: 'image' })}`,

  /** PNG of a single department's Daily report (dept_id required — one store). */
  dailyImagePath: (p: TimeReportParams) => `/api/time-report/daily/image${qs(clean(p))}`,
  /** Zip with one PNG per department for the current Daily filter. */
  dailyImagesZipPath: (p: TimeReportParams) => `/api/time-report/daily/images${qs(clean(p))}`,
}
