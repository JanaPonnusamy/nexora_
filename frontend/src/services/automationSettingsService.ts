import { api } from './apiClient'

export interface AutomationHealth {
  ok: boolean
  message: string
  root?: string
  branch?: string
  command?: string
  version?: string
}

export interface AutomationSettingsResponse {
  settings: {
    repo_path: string
    python_command: string
  }
  detected: {
    repo_path: string
    python_command: string
  }
  status: {
    git: AutomationHealth
    python: AutomationHealth
    automation: AutomationHealth
  }
  config_file: string
}

export const automationSettingsService = {
  get() {
    return api.get<AutomationSettingsResponse>('/api/automation/settings')
  },
  update(payload: { repo_path: string; python_command: string }) {
    return api.put<AutomationSettingsResponse>('/api/automation/settings', payload)
  },
}
