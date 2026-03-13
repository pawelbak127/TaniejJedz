'use client';

import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react';
import { Loader2 } from 'lucide-react';

type ButtonVariant = 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger';
type ButtonSize = 'sm' | 'md' | 'lg';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  icon?: ReactNode;
  fullWidth?: boolean;
}

const variantStyles: Record<ButtonVariant, string> = {
  primary: [
    'bg-[var(--color-primary)] text-[var(--color-text-inverse)]',
    'hover:bg-[var(--color-primary-hover)]',
    'active:bg-[var(--color-primary-hover)]',
    'disabled:bg-[var(--color-border)] disabled:text-[var(--color-text-tertiary)]',
  ].join(' '),
  secondary: [
    'bg-[var(--color-primary-light)] text-[var(--color-primary)]',
    'hover:bg-[#d6e6fb]',
    'active:bg-[#c5dbf9]',
    'disabled:bg-[var(--color-border)] disabled:text-[var(--color-text-tertiary)]',
  ].join(' '),
  outline: [
    'bg-transparent text-[var(--color-text-primary)]',
    'border border-[var(--color-border-strong)]',
    'hover:bg-[var(--color-bg)] hover:border-[var(--color-text-tertiary)]',
    'active:bg-[var(--color-border)]',
    'disabled:text-[var(--color-text-tertiary)] disabled:border-[var(--color-border)]',
  ].join(' '),
  ghost: [
    'bg-transparent text-[var(--color-text-secondary)]',
    'hover:bg-[var(--color-bg)] hover:text-[var(--color-text-primary)]',
    'active:bg-[var(--color-border)]',
    'disabled:text-[var(--color-text-tertiary)]',
  ].join(' '),
  danger: [
    'bg-[var(--color-danger)] text-[var(--color-text-inverse)]',
    'hover:bg-[#dc2626]',
    'active:bg-[#b91c1c]',
    'disabled:bg-[var(--color-border)] disabled:text-[var(--color-text-tertiary)]',
  ].join(' '),
};

const sizeStyles: Record<ButtonSize, string> = {
  sm: 'h-8 px-3 text-[var(--text-sm)] gap-1.5',
  md: 'h-10 px-4 text-[var(--text-base)] gap-2',
  lg: 'h-12 px-6 text-[var(--text-base)] gap-2.5',
};

const iconSizeMap: Record<ButtonSize, number> = {
  sm: 14,
  md: 16,
  lg: 18,
};

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      variant = 'primary',
      size = 'md',
      loading = false,
      icon,
      fullWidth = false,
      disabled,
      children,
      className = '',
      ...rest
    },
    ref,
  ) => {
    const isDisabled = disabled || loading;

    return (
      <button
        ref={ref}
        disabled={isDisabled}
        className={[
          'inline-flex items-center justify-center',
          'font-medium select-none',
          'rounded-[var(--radius-sm)]',
          'transition-colors duration-[var(--transition-fast)]',
          'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]',
          'disabled:cursor-not-allowed',
          variantStyles[variant],
          sizeStyles[size],
          fullWidth ? 'w-full' : '',
          className,
        ]
          .filter(Boolean)
          .join(' ')}
        {...rest}
      >
        {loading ? (
          <Loader2
            size={iconSizeMap[size]}
            className="animate-spin shrink-0"
            aria-hidden="true"
          />
        ) : icon ? (
          <span className="shrink-0" aria-hidden="true">
            {icon}
          </span>
        ) : null}
        {children && <span>{children}</span>}
      </button>
    );
  },
);

Button.displayName = 'Button';
export default Button;
