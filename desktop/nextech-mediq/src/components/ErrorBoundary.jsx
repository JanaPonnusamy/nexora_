import React from 'react';
import { ErrorState } from './states/ErrorState.jsx';

// Wraps each routed module so a defect in one module cannot take down the
// whole shell — per the "dedicated component boundary" requirement in
// Phase 2 §8.
export class ModuleErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error('[NexTech MediQ Workspace] module error boundary caught:', error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <ErrorState
          title="This module failed to load"
          message={this.state.error?.message}
          onRetry={() => this.setState({ error: null })}
        />
      );
    }
    return this.props.children;
  }
}
