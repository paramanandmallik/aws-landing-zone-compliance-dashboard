import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';

type ToastType = 'error' | 'success' | 'info';

interface Toast {
  id: number;
  message: string;
  type: ToastType;
  onRetry?: () => void;
}

interface ToastContextValue {
  showToast: (message: string, type?: ToastType, onRetry?: () => void) => void;
}

const ToastContext = createContext<ToastContextValue>({ showToast: () => {} });

let nextId = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const removeToast = useCallback((id: number) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  const showToast = useCallback((message: string, type: ToastType = 'info', onRetry?: () => void) => {
    const id = ++nextId;
    setToasts(prev => [...prev, { id, message, type, onRetry }]);
    setTimeout(() => removeToast(id), 5000);
  }, [removeToast]);

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      <div className="toast-container" role="status" aria-live="polite">
        {toasts.map(t => (
          <div key={t.id} className={`toast toast--${t.type}`}>
            <span className="toast-message">{t.message}</span>
            {t.type === 'error' && t.onRetry && (
              <button className="toast-retry" onClick={() => { removeToast(t.id); t.onRetry!(); }}>
                Retry
              </button>
            )}
            <button className="toast-close" onClick={() => removeToast(t.id)} aria-label="Close notification">
              ×
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}
