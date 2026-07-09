import type { ReactNode } from 'react'
import { Group, Separator, useDefaultLayout } from 'react-resizable-panels'

export { Panel as DockPanelItem } from 'react-resizable-panels'

interface DockGroupProps {
  id: string
  orientation?: 'horizontal' | 'vertical'
  children: ReactNode
}

/**
 * Wraps react-resizable-panels' Group with automatic localStorage-backed
 * layout persistence (spec item 17) — panel sizes survive a reload without
 * any module needing to wire that up itself. Modules use DockGroup +
 * DockPanelItem + DockSeparator directly to build their own multi-panel
 * layouts (grid + decision panel, grid + charts, etc.); the platform only
 * hosts one module at a time in its own top-level panel (see WorkspaceHost).
 */
export function DockGroup({ id, orientation = 'horizontal', children }: DockGroupProps) {
  const { defaultLayout, onLayoutChanged } = useDefaultLayout({
    id: `uninex.layout.dock.${id}`,
    storage: typeof window !== 'undefined' ? window.localStorage : undefined,
  })

  return (
    <Group id={id} orientation={orientation} defaultLayout={defaultLayout} onLayoutChanged={onLayoutChanged}>
      {children}
    </Group>
  )
}

export function DockSeparator() {
  return <Separator className="platform-dock__separator" />
}
