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
            className="text-sm font-medium text-text-primary"
          >
            {label}
          </label>
        )}

        <div className="relative">
          {icon && (
            <span
              className="absolute left-3 top-1/2 -translate-y-1/2 text-text-tertiary pointer-events-none"
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
              'w-full h-10 px-3 text-base',
              'bg-surface',
              'border rounded-sm',
              'text-text-primary',
              'placeholder:text-text-tertiary',
              'transition-colors duration-fast',
              'focus:outline-none focus:ring-2 focus:ring-offset-0',
              error
                ? 'border-danger focus:ring-danger/30'
                : 'border-border hover:border-border-strong focus:border-primary focus:ring-primary/20',
              'disabled:bg-bg disabled:text-text-tertiary disabled:cursor-not-allowed',
              icon ? 'pl-10' : '',
            ].join(' ')}
            {...rest}
          />
        </div>

        {error && (
          <p
            id={errorId}
            className="text-xs text-danger"
            role="alert"
          >
            {error}
          </p>
        )}

        {helperText && !error && (
          <p
            id={helperId}
            className="text-xs text-text-tertiary"
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
