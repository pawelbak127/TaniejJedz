'use client';

import { forwardRef, useId, type InputHTMLAttributes, type ReactNode } from 'react';

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
  icon?: ReactNode;
  fullWidth?: boolean;
}

const Input = forwardRef<HTMLInputElement, InputProps>(
  (
    {
      label,
      error,
      helperText,
      icon,
      fullWidth = true,
      className = '',
      id: externalId,
      ...rest
    },
    ref,
  ) => {
    const generatedId = useId();
    const inputId = externalId || generatedId;
    const errorId = error ? `${inputId}-error` : undefined;
    const helperId = helperText && !error ? `${inputId}-helper` : undefined;

    return (
      <div className={`flex flex-col gap-1.5 ${fullWidth ? 'w-full' : ''} ${className}`}>
        {label && (
          <label
            htmlFor={inputId}
            className="text-[var(--text-sm)] font-medium text-[var(--color-text-primary)]"
          >
            {label}
          </label>
        )}

        <div className="relative">
          {icon && (
            <span
              className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-tertiary)] pointer-events-none"
              aria-hidden="true"
            >
              {icon}
            </span>
          )}

          <input
            ref={ref}
            id={inputId}
            aria-invalid={!!error}
            aria-describedby={errorId || helperId}
            className={[
              'w-full h-10 px-3 text-[var(--text-base)]',
              'bg-[var(--color-surface)]',
              'border rounded-[var(--radius-sm)]',
              'text-[var(--color-text-primary)]',
              'placeholder:text-[var(--color-text-tertiary)]',
              'transition-colors duration-[var(--transition-fast)]',
              'focus:outline-none focus:ring-2 focus:ring-offset-0',
              error
                ? 'border-[var(--color-danger)] focus:ring-[var(--color-danger)]/30'
                : 'border-[var(--color-border)] hover:border-[var(--color-border-strong)] focus:border-[var(--color-primary)] focus:ring-[var(--color-primary)]/20',
              'disabled:bg-[var(--color-bg)] disabled:text-[var(--color-text-tertiary)] disabled:cursor-not-allowed',
              icon ? 'pl-10' : '',
            ].join(' ')}
            {...rest}
          />
        </div>

        {error && (
          <p
            id={errorId}
            className="text-[var(--text-xs)] text-[var(--color-danger)]"
            role="alert"
          >
            {error}
          </p>
        )}

        {helperText && !error && (
          <p
            id={helperId}
            className="text-[var(--text-xs)] text-[var(--color-text-tertiary)]"
          >
            {helperText}
          </p>
        )}
      </div>
    );
  },
);

Input.displayName = 'Input';
export default Input;
