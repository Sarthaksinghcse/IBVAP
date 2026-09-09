import React, { Component, ErrorInfo, ReactNode } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface Props {
  children: ReactNode;
  fallbackTitle?: string;
  fallbackMessage?: string;
  onReset?: () => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
    errorInfo: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error, errorInfo: null };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    this.setState({ error, errorInfo });
    console.error('[ERROR] Caught by React ErrorBoundary:', error);
    console.error('[ERROR] Component stack:', errorInfo.componentStack);
  }

  public handleReset = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
    if (this.props.onReset) {
      this.props.onReset();
    }
  };

  public render() {
    if (this.state.hasError) {
      const title = this.props.fallbackTitle || 'Component Display Error';
      const message =
        this.props.fallbackMessage ||
        'An unexpected error occurred while rendering this component. The rest of the SHIELD application remains active.';

      return (
        <div className="bg-[#121419] light:bg-white border border-red-500/40 rounded-2xl p-6 flex flex-col items-center justify-center text-center my-2 shadow-card">
          <div className="w-12 h-12 rounded-full bg-red-500/15 border border-red-500/30 flex items-center justify-center text-red-400 mb-3">
            <AlertTriangle size={24} />
          </div>
          <h4 className="text-sm font-bold text-red-300 light:text-red-700 uppercase tracking-wide">
            {title}
          </h4>
          <p className="text-xs text-slate-400 light:text-slate-600 mt-1 mb-3 max-w-md leading-relaxed">
            {message}
          </p>
          {this.state.error && (
            <div className="bg-black/60 light:bg-slate-100 p-2.5 rounded-lg border border-red-500/20 text-[10px] font-mono text-red-400 light:text-red-600 max-w-md w-full overflow-x-auto text-left mb-4">
              {this.state.error.toString()}
            </div>
          )}
          <button
            type="button"
            onClick={this.handleReset}
            className="ibvap-btn-ghost text-xs py-1.5 px-3 flex items-center gap-1.5 cursor-pointer hover:border-red-500/50"
          >
            <RefreshCw size={12} /> Retry Component
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
