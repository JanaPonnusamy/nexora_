import type { ReactNode } from 'react'

interface WorkspaceContainerProps {
  children: ReactNode
  className?: string
}

export function WorkspaceContainer({ children, className = '' }: WorkspaceContainerProps) {
  return <section className={`ds-workspace ${className}`.trim()}>{children}</section>
}
