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
    'bg-primary text-text-inverse',
    'hover:bg-primary-hover',
    'active:bg-primary-hover',
    'disabled:bg-border disabled:text-text-tertiary',
  ].join(' '),
  secondary: [
    'bg-primary-light text-primary',
    'hover:bg-[#d6e6fb]',
    'active:bg-[#c5dbf9]',
    'disabled:bg-border disabled:text-text-tertiary',
  ].join(' '),
  outline: [
    'bg-transparent text-text-primary',
    'border border-border-strong',
    'hover:bg-bg hover:border-text-tertiary',
    'active:bg-border',
    'disabled:text-text-tertiary disabled:border-border',
  ].join(' '),
  ghost: [
    'bg-transparent text-text-secondary',
    'hover:bg-bg hover:text-text-primary',
    'active:bg-border',
    'disabled:text-text-tertiary',
  ].join(' '),
  danger: [
    'bg-danger text-text-inverse',
    'hover:bg-[#dc2626]',
    'active:bg-[#b91c1c]',
    'disabled:bg-border disabled:text-text-tertiary',
  ].join(' '),
};

const sizeStyles: Record<ButtonSize, string> = {
  sm: 'h-8 px-3 text-sm gap-1.5',
  md: 'h-10 px-4 text-base gap-2',
  lg: 'h-12 px-6 text-base gap-2.5',
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
          'rounded-sm',
          'transition-colors duration-fast',
          'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary',
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
