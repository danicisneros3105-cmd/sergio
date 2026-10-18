import { Component } from 'react';
import type { ReactNode, ErrorInfo } from 'react';
import { AlertTriangle, RotateCcw } from 'lucide-react';
import { dropOldCopy } from '../lib/freshness';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

function isChunkLoadError(error: Error | null): boolean {
  const msg = error?.message || '';
  return /Failed to fetch dynamically imported module|Importing a module script failed|ChunkLoadError|error loading dynamically imported module/i.test(
    msg,
  );
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('ErrorBoundary caught:', error, info);
    if (isChunkLoadError(error)) {
      const key = 'sergio-chunk-reload';
      try {
        const last = Number(sessionStorage.getItem(key) || '0');
        if (Date.now() - last > 10_000) {
          sessionStorage.setItem(key, String(Date.now()));
          void dropOldCopy().finally(() => {
            window.location.reload();
          });
        }
      } catch {
        void dropOldCopy().finally(() => {
          window.location.reload();
        });
      }
    }
  }

  private handleRecover = () => {
    if (isChunkLoadError(this.state.error)) {
      void dropOldCopy().finally(() => {
        window.location.reload();
      });
      return;
    }
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      const chunkErr = isChunkLoadError(this.state.error);
      return (
        <div className="flex items-center justify-center h-full p-8" style={{ background: 'var(--color-bg)' }}>
          <div className="text-center max-w-sm">
            <div
              className="w-12 h-12 rounded-2xl flex items-center justify-center mx-auto mb-4"
              style={{ background: 'rgba(220,38,38,0.1)', color: 'var(--color-error)' }}
            >
              <AlertTriangle size={24} />
            </div>
            <h2 className="text-lg font-semibold mb-2" style={{ color: 'var(--color-text)' }}>
              {chunkErr ? 'Actualizando la aplicación…' : 'Algo salió mal'}
            </h2>
            <p className="text-sm mb-4" style={{ color: 'var(--color-text-secondary)' }}>
              {chunkErr
                ? 'Se instaló una versión nueva de Sergio. Recargue para abrir esta sección.'
                : this.state.error?.message || 'Ocurrió un error inesperado.'}
            </p>
            <button
              onClick={this.handleRecover}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors cursor-pointer"
              style={{ background: 'var(--color-accent)', color: 'var(--color-on-accent)' }}
            >
              <RotateCcw size={14} />
              {chunkErr ? 'Recargar ahora' : 'Reintentar'}
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

