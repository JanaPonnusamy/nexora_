import { api } from './apiClient'

export interface WhatsAppProfile {
  profile_id: string
  profile_name: string
  owner_type: string
  owner_name: string
  tenant_id: string
  store_id: string
  default_phone: string
  notes: string
  is_default: boolean
  session_dir: string
  created_at: string
  updated_at: string
  last_used_at: string
}

export interface WhatsAppCapabilities {
  browser_detected: boolean
  browser_command: string
  selenium_available: boolean
  delivery_mode: 'manual_browser' | 'selenium'
  headless: boolean
  manual_fallback: boolean
  can_launch_qr: boolean
  can_auto_send_attachment: boolean
  can_read_messages: boolean
  profile_count: number
  default_profile_id: string
}

export interface WhatsAppState {
  settings: {
    browser_command: string
    delivery_mode: 'manual_browser' | 'selenium'
    launch_wait_seconds: number
    headless: boolean
    manual_fallback: boolean
  }
  profiles: WhatsAppProfile[]
  targets: WhatsAppTarget[]
  messages: WhatsAppMessage[]
  send_log?: WhatsAppSendLogEntry[]
  capabilities: WhatsAppCapabilities
}

export interface WhatsAppChat {
  name: string
  kind: 'group' | 'contact'
}

export interface WhatsAppChatList {
  profile_id: string
  chats: WhatsAppChat[]
  count: number
  group_count: number
  checked_at: string
}

export interface WhatsAppSendLogEntry {
  id: string
  profile_id: string
  profile_name: string
  target_name: string
  kind: string
  status: 'sent' | 'failed' | string
  message_preview: string
  error: string
  snapshot: string
  at: string
}

export interface WhatsAppSendResult {
  status: string
  message: string
  mode?: string
  url?: string
  target_hint?: string
  attachment_path?: string
}

export interface WhatsAppTarget {
  target_id: string
  profile_id: string
  target_kind: 'contact' | 'group'
  target_name: string
  target_ref: string
  can_send: boolean
  can_read: boolean
  is_active: boolean
  notes: string
  created_at: string
  updated_at: string
  last_synced_at: string
}

export interface WhatsAppMessage {
  message_id: string
  target_id: string
  profile_id: string
  direction: 'incoming' | 'outgoing'
  message_text: string
  message_time: string
  source_label: string
  captured_at: string
}

export const whatsappService = {
  getState() {
    return api.get<WhatsAppState>('/api/whatsapp/state')
  },
  saveSettings(payload: {
    browser_command: string
    delivery_mode: 'manual_browser' | 'selenium'
    launch_wait_seconds: number
    headless?: boolean
    manual_fallback?: boolean
  }) {
    return api.put<WhatsAppState>('/api/whatsapp/settings', payload)
  },
  saveProfile(payload: {
    profile_id?: string
    profile_name: string
    owner_type: string
    owner_name: string
    tenant_id: string
    store_id: string
    default_phone: string
    notes: string
    is_default: boolean
  }) {
    return api.post<{
      profiles: WhatsAppProfile[]
      profile: WhatsAppProfile
      capabilities: WhatsAppCapabilities
    }>('/api/whatsapp/profiles', payload)
  },
  deleteProfile(profileId: string) {
    return api.delete<{
      profiles: WhatsAppProfile[]
      targets: WhatsAppTarget[]
      messages: WhatsAppMessage[]
      capabilities: WhatsAppCapabilities
    }>(`/api/whatsapp/profiles/${profileId}`)
  },
  launchProfile(profileId: string) {
    return api.post<{
      status: string
      message: string
      mode: string
      url: string
      attachment_path?: string
    }>(`/api/whatsapp/profiles/${profileId}/launch`, {})
  },
  checkProfileStatus(profileId: string) {
    return api.get<{
      profile_id: string
      logged_in: boolean
      checked_at: string
    }>(`/api/whatsapp/profiles/${profileId}/status`)
  },
  loginQr(profileId: string) {
    return api.get<{
      profile_id: string
      logged_in: boolean
      qr_data_uri: string | null
      checked_at: string
    }>(`/api/whatsapp/profiles/${profileId}/qr`)
  },
  logoutProfile(profileId: string) {
    return api.post<{
      profile_id: string
      logged_in: boolean
      profiles: WhatsAppProfile[]
      capabilities: WhatsAppCapabilities
    }>(`/api/whatsapp/profiles/${profileId}/logout`, {})
  },
  sendFile(profileId: string, phone: string, message: string, file: File) {
    const form = new FormData()
    form.append('profile_id', profileId)
    form.append('phone', phone)
    form.append('message', message)
    form.append('file', file)
    return api.upload<{
      status: string
      message: string
      mode: string
      url: string
      attachment_path?: string
    }>('/api/whatsapp/send/file', form)
  },
  saveTarget(payload: {
    target_id?: string
    profile_id: string
    target_kind: string
    target_name: string
    target_ref: string
    can_send: boolean
    can_read: boolean
    is_active: boolean
    notes: string
  }) {
    return api.post<{
      targets: WhatsAppTarget[]
      target: WhatsAppTarget
      messages: WhatsAppMessage[]
      capabilities: WhatsAppCapabilities
    }>('/api/whatsapp/targets', payload)
  },
  deleteTarget(targetId: string) {
    return api.delete<{
      targets: WhatsAppTarget[]
      messages: WhatsAppMessage[]
      capabilities: WhatsAppCapabilities
    }>(`/api/whatsapp/targets/${targetId}`)
  },
  syncTarget(targetId: string, limit = 20) {
    return api.post<{
      targets: WhatsAppTarget[]
      messages: WhatsAppMessage[]
      synced_count: number
      target: WhatsAppTarget
      capabilities: WhatsAppCapabilities
    }>(`/api/whatsapp/targets/${targetId}/sync?limit=${limit}`, {})
  },
  sendTargetFile(targetId: string, message: string, file: File) {
    const form = new FormData()
    form.append('target_id', targetId)
    form.append('message', message)
    form.append('file', file)
    return api.upload<{
      status: string
      message: string
      mode: string
      url: string
      attachment_path?: string
    }>('/api/whatsapp/targets/send-file', form)
  },
  listChats(profileId: string) {
    return api.get<WhatsAppChatList>(`/api/whatsapp/profiles/${profileId}/chats`)
  },
  sendChat(profileId: string, chatName: string, message: string) {
    return api.post<WhatsAppSendResult>('/api/whatsapp/send/chat', {
      profile_id: profileId,
      chat_name: chatName,
      message,
    })
  },
  sendChatFile(profileId: string, chatName: string, message: string, file: File) {
    const form = new FormData()
    form.append('profile_id', profileId)
    form.append('chat_name', chatName)
    form.append('message', message)
    form.append('file', file)
    return api.upload<WhatsAppSendResult>('/api/whatsapp/send/chat-file', form)
  },
  getSendLog(limit = 100) {
    return api.get<{ entries: WhatsAppSendLogEntry[]; count: number }>(
      `/api/whatsapp/send-log?limit=${limit}`,
    )
  },
}
