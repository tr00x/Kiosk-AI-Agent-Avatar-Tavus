/**
 * ErrorBoundary — Catches React render errors and shows a recovery screen.
 * Prevents the entire kiosk from going blank on an unhandled exception.
 */

import React from 'react';

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    console.error('[ErrorBoundary] Caught:', error, info?.componentStack);
  }

  handleRestart = () => {
    this.setState({ hasError: false, error: null });
    // Clear any lingering session state
    try { sessionStorage.clear(); } catch (_) {}
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="error-boundary">
          <div className="error-boundary-icon">!</div>
          <h2 className="error-boundary-title">Something went wrong</h2>
          <p className="error-boundary-text">
            The kiosk encountered an error. Tap below to restart.
          </p>
          <button className="error-boundary-btn" onClick={this.handleRestart}>
            Restart Kiosk
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
