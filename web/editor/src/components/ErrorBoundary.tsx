import React, { Component, ErrorInfo, ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Editor error:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: 24, fontFamily: 'system-ui', maxWidth: 600, margin: '40px auto' }}>
          <h2 style={{ color: '#dc2626' }}>编辑器加载出错</h2>
          <pre style={{ 
            background: '#fef2f2', padding: 16, borderRadius: 8, 
            overflow: 'auto', fontSize: 13, color: '#991b1b',
            whiteSpace: 'pre-wrap', wordBreak: 'break-all'
          }}>
            {this.state.error?.message || 'Unknown error'}
            {'\n\n'}
            {this.state.error?.stack || ''}
          </pre>
          <button 
            onClick={() => { localStorage.clear(); window.location.reload(); }}
            style={{ marginTop: 16, padding: '8px 16px', cursor: 'pointer' }}
          >
            清除缓存并刷新
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
