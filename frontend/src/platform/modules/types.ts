import type { ComponentType } from 'react'
import type { Capability } from '../../types/access'

export type ModuleId = string

export interface ModuleContext {
  moduleId: ModuleId
}

// Every desktop module implements the same lifecycle; the shell drives it
// (via ModuleLifecycleController) — modules never manipulate the shell
// directly. All hooks are optional so a simple module (e.g. Reports) only
// implements what it actually needs.
export interface ModuleLifecycle {
  initialize?: (ctx: ModuleContext) => void | Promise<void>
  load?: (ctx: ModuleContext) => void | Promise<void>
  activate?: (ctx: ModuleContext) => void | Promise<void>
  deactivate?: (ctx: ModuleContext) => void | Promise<void>
  saveState?: (ctx: ModuleContext) => void | Promise<void>
  restoreState?: (ctx: ModuleContext) => void | Promise<void>
  dispose?: (ctx: ModuleContext) => void | Promise<void>
}

export interface RibbonCommand {
  id: string
  label: string
  icon?: string
  shortcut?: string
  onExecute: () => void
}

export interface RibbonGroup {
  id: string
  label: string
  commands: RibbonCommand[]
}

// A module contributes one or more ribbon tabs; the platform's Home/Help
// tabs are not module contributions.
export interface RibbonContribution {
  tab: string
  groups: RibbonGroup[]
}

export interface NavContribution {
  id: string
  label: string
  icon?: string
  group: string
  path: string
  /** Gates visibility via the existing useAccess()/RoleContext capability system. */
  capability?: Capability
}

export interface ModuleDefinition {
  id: ModuleId
  title: string
  icon?: string
  nav: NavContribution
  ribbon?: RibbonContribution
  component: ComponentType<ModuleContext>
  lifecycle?: ModuleLifecycle
}
