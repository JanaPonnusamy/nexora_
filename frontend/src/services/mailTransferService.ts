import { api } from './apiClient'

export interface FileTransferStatus {
  enabled: boolean
  transport_mode: string | null
  tick_seconds: number
  receiver: { at: string | null; summary: Record<string, number> | null; error: string | null } | null
}

export interface MailConfig {
  enabled: boolean
  mode: string | null
  smtp_host: string | null
  smtp_port: number | null
  imap_host: string | null
  imap_port: number | null
  imap_folder: string | null
  username: string | null
  password_env: string | null
  password_env_set: boolean
  default_store_address: string | null
}

export interface MailTestResult {
  ok: boolean
  detail: string
}

export interface FileSyncPackage {
  package_id: string
  execution_id: string
  tenant_id: string | null
  store_id: string | null
  source_filename: string
  checksum: string
  transport_mode: string | null
  status: string
  total_rows: number | null
  total_chunks: number | null
  total_tables: number | null
  tables_imported: number | null
  tables_failed: number | null
  received_at: string
  import_started_at: string | null
  import_completed_at: string | null
  error_message: string | null
}

export const mailTransferService = {
  status: () => api.get<FileTransferStatus>('/api/sync/file-transfer/status'),
  packages: (status?: string, limit = 100) =>
    api.get<FileSyncPackage[]>(
      `/api/sync/file-transfer/packages?limit=${limit}${status ? `&status=${status}` : ''}`
    ),
  mailConfig: () => api.get<MailConfig>('/api/sync/file-transfer/mail-config'),
  testSmtp: () => api.post<MailTestResult>('/api/sync/file-transfer/mail-config/test-smtp', {}),
  testImap: () => api.post<MailTestResult>('/api/sync/file-transfer/mail-config/test-imap', {}),
}
