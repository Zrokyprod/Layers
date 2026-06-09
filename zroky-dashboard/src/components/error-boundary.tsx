"use client";

import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  override componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("ErrorBoundary caught an error:", error, errorInfo);
  }

  private handleRetry = () => {
    this.setState({ hasError: false, error: undefined });
    window.location.reload();
  };

  override render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="errb-screen">
          <div className="errb-card">
            <div className="errb-icon-wrap" aria-hidden="true">⚠</div>
            <h2 className="errb-heading">Something went wrong</h2>
            <p className="errb-message">
              {this.state.error?.message || "An unexpected error occurred"}
            </p>
            <button type="button" className="btn btn-primary" onClick={this.handleRetry}>
              ↺ Retry
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
