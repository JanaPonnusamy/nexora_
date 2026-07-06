import type { Capability } from './access'

export interface NavLinkItem {
  label: string
  to: string
  icon: string
  cap?: Capability
}

export type NavEntry =
  | ({ kind: 'link' } & NavLinkItem)
  | { kind: 'group'; label: string; icon: string; cap?: Capability; children: NavLinkItem[] }
