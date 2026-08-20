import type { CSSProperties, ReactNode } from 'react'
import { WorkspaceContainer } from './WorkspaceContainer'

interface WorkspaceShellProps {
  header: ReactNode
  kpis?: ReactNode
  filters?: ReactNode
  children: ReactNode
  statusBar?: ReactNode
  className?: string
  fullWidth?: boolean
  style?: CSSProperties
}

export function WorkspaceShell({
  header,
  kpis,
  filters,
  children,
  statusBar,
  className = '',
  fullWidth = false,
  style,
}: WorkspaceShellProps) {
  const shell = (
    <div className={`ds-workspace-shell ${className}`.trim()} style={style}>
      <div className="ds-workspace-shell__header">{header}</div>
      {kpis && <div className="ds-workspace-shell__kpis">{kpis}</div>}
      {filters && <div className="ds-workspace-shell__filters">{filters}</div>}
      <div className="ds-workspace-shell__body">{children}</div>
      {statusBar && <div className="ds-workspace-shell__status">{statusBar}</div>}
    </div>
  )

  return fullWidth ? shell : <WorkspaceContainer>{shell}</WorkspaceContainer>
}
