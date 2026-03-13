'use client';

import {
  useEffect,
  useRef,
  useCallback,
  type ReactNode,
  type KeyboardEvent,
} from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  maxWidth?: string;
}

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'textarea:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ');

export default function Modal({
  open,
  onClose,
  title,
  children,
  maxWidth = '480px',
}: ModalProps) {
  const overlayRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  const trapFocus = useCallback((e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== 'Tab' || !panelRef.current) return;

    const focusable = panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR);
    if (focusable.length === 0) return;

    const first = focusable[0];
    const last = focusable[focusable.length - 1];

    if (e.shiftKey) {
      if (document.activeElement === first) {
        e.preventDefault();
        last.focus();
      }
    } else {
      if (document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  }, []);

  useEffect(() => {
    if (open) {
      previousFocusRef.current = document.activeElement as HTMLElement;
      document.body.style.overflow = 'hidden';

      requestAnimationFrame(() => {
        const focusable = panelRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR);
        if (focusable && focusable.length > 0) {
          focusable[0].focus();
        } else {
          panelRef.current?.focus();
        }
      });
    } else {
      document.body.style.overflow = '';
      previousFocusRef.current?.focus();
    }

    return () => {
      document.body.style.overflow = '';
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;

    const handleKeyDown = (e: globalThis.KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  const handleOverlayClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === overlayRef.current) {
      onClose();
    }
  };

  const modal = (
    <div
      ref={overlayRef}
      onClick={handleOverlayClick}
      onKeyDown={trapFocus}
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="presentation"
    >
      <div
        className="fixed inset-0 bg-black/30 animate-fade-in"
        aria-hidden="true"
      />

      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className="relative z-10 w-full bg-[var(--color-surface)] rounded-[var(--radius-lg)] border border-[var(--color-border)] animate-modal-in"
        style={{
          maxWidth,
          boxShadow: 'var(--shadow-xl)',
          maxHeight: 'calc(100vh - 2rem)',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--color-border)]">
          <h2 className="text-[var(--text-lg)] font-semibold text-[var(--color-text-primary)]">
            {title}
          </h2>
          <button
            onClick={onClose}
            className="p-1.5 rounded-[var(--radius-sm)] text-[var(--color-text-tertiary)] hover:text-[var(--color-text-secondary)] hover:bg-[var(--color-bg)] transition-colors duration-[var(--transition-fast)]"
            aria-label="Zamknij"
          >
            <X size={18} />
          </button>
        </div>

        <div className="px-6 py-4 overflow-y-auto flex-1">{children}</div>
      </div>

      <style jsx>{`
        @keyframes fade-in {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        @keyframes modal-in {
          from {
            opacity: 0;
            transform: scale(0.96) translateY(8px);
          }
          to {
            opacity: 1;
            transform: scale(1) translateY(0);
          }
        }
        .animate-fade-in {
          animation: fade-in 150ms ease-out;
        }
        .animate-modal-in {
          animation: modal-in 200ms ease-out;
        }
      `}</style>
    </div>
  );

  if (typeof document === 'undefined') return null;
  return createPortal(modal, document.body);
}
