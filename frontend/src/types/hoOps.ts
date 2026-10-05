// HO backend self-update / fleet status (modules/ho_ops).

export interface HoNodeStatus {
  url: string | null
  label?: string | null
  is_self: boolean
  reachable: boolean
  error?: string
  hostname?: string
  platform?: string
  kind?: 'git' | 'exe' | 'unknown'
  is_git?: boolean
  branch?: string | null
  head?: string | null
  subject?: string | null
  committed_at?: string | null
  behind_main?: number | null
  up_to_date?: boolean | null
  dirty?: boolean
  fleet_routes?: number
  can_self_update?: boolean
  deploy_script?: string | null
  // exe nodes
  install_dir?: string
  service_name?: string
  exe_version?: string | null
  latest_release?: string | null
}

export interface SelfUpdateResult {
  started: boolean
  reason?: string
  hostname?: string
  from_head?: string
  message?: string
}

export interface UpdateNodeTarget {
  url: string | null
  is_self: boolean
}

export interface UpdateNodesResult {
  results: Array<{
    url: string | null
    is_self?: boolean
    ok: boolean
    error?: string
    result?: SelfUpdateResult
  }>
}
