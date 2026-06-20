export interface NavLinkItem {
  label: string
  to: string
  icon: string
}

export type NavEntry =
  | ({ kind: 'link' } & NavLinkItem)
  | { kind: 'group'; label: string; icon: string; children: NavLinkItem[] }
