import { Component, type ErrorInfo, type ReactNode } from 'react'
import { ErrorState } from '../../components/common/ErrorState'
import { errorService } from './ErrorService'

interface Props {
  scope: string
  children: ReactNode
}

interface State {
  hasError: boolean
}

/**
 * Crash barrier for a module's render tree — a rendering exception in one
 * module must not take down the whole desktop shell. Reports through the
 * same ErrorService as runtime (non-render) failures so there's one place
 * errors are observed, not two.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    errorService.report(this.props.scope, error.message, { error, componentStack: info.componentStack })
  }

  render() {
    if (this.state.hasError) {
      return (
        <ErrorState
          title="This section crashed"
          description="An unexpected error occurred. Try reloading the workspace."
          onRetry={() => this.setState({ hasError: false })}
        />
      )
    }
    return this.props.children
  }
}
