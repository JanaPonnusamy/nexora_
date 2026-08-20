import type { ReactNode } from 'react'
import { Group, Panel, Separator } from 'react-resizable-panels'

interface SplitViewProps {
  primary: ReactNode
  secondary?: ReactNode
  tertiary?: ReactNode
  direction?: 'horizontal' | 'vertical'
  className?: string
  primaryDefault?: number
  secondaryDefault?: number
  tertiaryDefault?: number
}

export function SplitView({
  primary,
  secondary,
  tertiary,
  direction = 'horizontal',
  className = '',
  primaryDefault = 60,
  secondaryDefault = 40,
  tertiaryDefault = 24,
}: SplitViewProps) {
  if (!secondary) {
    return <div className={`ds-split-view ds-split-view--single ${className}`.trim()}>{primary}</div>
  }

  if (!tertiary) {
    return (
      <Group orientation={direction} className={`ds-split-view ${className}`.trim()}>
        <Panel defaultSize={primaryDefault} minSize={35}>
          <div className="ds-split-view__panel">{primary}</div>
        </Panel>
        <Separator className="ds-split-view__handle" />
        <Panel defaultSize={secondaryDefault} minSize={20}>
          <div className="ds-split-view__panel">{secondary}</div>
        </Panel>
      </Group>
    )
  }

  return (
    <Group orientation={direction} className={`ds-split-view ${className}`.trim()}>
      <Panel defaultSize={primaryDefault} minSize={30}>
        <div className="ds-split-view__panel">{primary}</div>
      </Panel>
      <Separator className="ds-split-view__handle" />
      <Panel defaultSize={Math.max(secondaryDefault - tertiaryDefault, 20)} minSize={18}>
        <div className="ds-split-view__panel">{secondary}</div>
      </Panel>
      <Separator className="ds-split-view__handle" />
      <Panel defaultSize={tertiaryDefault} minSize={16}>
        <div className="ds-split-view__panel">{tertiary}</div>
      </Panel>
    </Group>
  )
}
