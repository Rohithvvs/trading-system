import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallbackTitle?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("Uncaught error caught by ErrorBoundary:", error, errorInfo);
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div
          style={{
            padding: "24px",
            margin: "16px",
            borderRadius: "var(--radius-lg, 12px)",
            background: "var(--surface, #141a22)",
            border: "1px solid var(--negative, #ef4444)",
            color: "var(--text, #f0f4f8)",
          }}
          data-testid="error-boundary-fallback"
        >
          <h3 style={{ margin: "0 0 8px 0", color: "var(--negative-text, #f87171)" }}>
            {this.props.fallbackTitle || "Something went wrong in this component"}
          </h3>
          <p style={{ fontSize: "0.875rem", color: "var(--text-muted)", margin: "0 0 16px 0" }}>
            {this.state.error?.message || "An unexpected error occurred."}
          </p>
          <button
            type="button"
            className="ds-btn ds-btn--secondary ds-btn--sm"
            onClick={() => this.setState({ hasError: false, error: null })}
          >
            Try Again
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
