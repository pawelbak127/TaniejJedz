'use client';

import {
  createContext,
  useCallback,
  useContext,
  useState,
  useRef,
  useEffect,
  type ReactNode,
} from 'react';
import { X, CheckCircle2, AlertCircle, Info } from 'lucide-react';
import { MAX_TOASTS, TOAST_DURATION_MS } from '@/lib/constants';

type ToastType = 'success' | 'error' | 'info';

interface Toast {
  id: string;
  message: string;
  type: ToastType;
  duration: number;
}

interface ToastContextValue {
  addToast: (message: string, type?: ToastType, duration?: number) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error('useToast must be used within ToastProvider');
  }
  return ctx;
}

let toastCounter = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const timersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const removeToast = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
    const timer = timersRef.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timersRef.current.delete(id);
    }
  }, []);

  const addToast = useCallback(
    (message: string, type: ToastType = 'info', duration: number = TOAST_DURATION_MS) => {
      const id = `toast-${++toastCounter}`;
      const toast: Toast = { id, message, type, duration };

      setToasts(prev => {
        const next = [...prev, toast];
        if (next.length > MAX_TOASTS) {
          const removed = next.shift();
          if (removed) {
            const timer = timersRef.current.get(removed.id);
            if (timer) {
              clearTimeout(timer);
              timersRef.current.delete(removed.id);
            }
          }
        }
        return next;
      });

      const timer = setTimeout(() => removeToast(id), duration);
      timersRef.current.set(id, timer);
    },
    [removeToast],
  );

  useEffect(() => {
    return () => {
      timersRef.current.forEach(timer => clearTimeout(timer));
    };
  }, []);

  return (
    <ToastContext.Provider value={{ addToast }}>
      {children}
      <ToastContainer toasts={toasts} onDismiss={removeToast} />
    </ToastContext.Provider>
  );
}

const iconMap: Record<ToastType, typeof CheckCircle2> = {
  success: CheckCircle2,
  error: AlertCircle,
  info: Info,
};

const iconColorMap: Record<ToastType, string> = {
  success: 'text-accent-dark',
  error: 'text-danger',
  info: 'text-primary',
};

function ToastContainer({
  toasts,
  onDismiss,
}: {
  toasts: Toast[];
  onDismiss: (id: string) => void;
}) {
  if (toasts.length === 0) return null;

  return (
    <div
      className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 flex flex-col gap-2 w-[calc(100%-2rem)] max-w-[400px]"
      aria-live="polite"
      aria-label="Powiadomienia"
    >
      {toasts.map(toast => {
        const Icon = iconMap[toast.type];
        return (
          <div
            key={toast.id}
            className="flex items-start gap-3 p-3 rounded-md bg-surface border border-border shadow-lg animate-slide-up"
            role="alert"
          >
            <Icon
              size={18}
              className={`shrink-0 mt-0.5 ${iconColorMap[toast.type]}`}
              aria-hidden="true"
            />
            <p className="flex-1 text-sm text-text-primary leading-snug">
              {toast.message}
            </p>
            <button
              onClick={() => onDismiss(toast.id)}
              className="shrink-0 p-0.5 rounded-sm text-text-tertiary hover:text-text-secondary hover:bg-bg transition-colors duration-fast"
              aria-label="Zamknij powiadomienie"
            >
              <X size={14} />
            </button>
          </div>
        );
      })}

      <style jsx>{`
        @keyframes slide-up {
          from {
            opacity: 0;
            transform: translateY(8px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
        .animate-slide-up {
          animation: slide-up 200ms ease-out;
        }
      `}</style>
    </div>
  );
}
