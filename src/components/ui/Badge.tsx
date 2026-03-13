import type { ReactNode } from 'react';

type BadgeVariant = 'filled' | 'outline' | 'dot';
type BadgeSize = 'sm' | 'md';

interface BadgeProps {
  children: ReactNode;
  variant?: BadgeVariant;
  size?: BadgeSize;
  color?: string;
  dotColor?: string;
  className?: string;
}

const sizeStyles: Record<BadgeSize, string> = {
  sm: 'h-5 px-1.5 text-[var(--text-xs)]',
  md: 'h-6 px-2.5 text-[var(--text-sm)]',
};

export default function Badge({
  children,
  variant = 'filled',
  size = 'sm',
  color,
  dotColor,
  className = '',
}: BadgeProps) {
  if (variant === 'dot') {
    return (
      <span
        className={[
          'inline-flex items-center gap-1.5',
          'font-medium',
          sizeStyles[size],
          className,
        ].join(' ')}
        style={{ color: color || 'var(--color-text-secondary)' }}
      >
        <span
          className="w-2 h-2 rounded-full shrink-0"
          style={{ backgroundColor: dotColor || color || 'var(--color-text-tertiary)' }}
          aria-hidden="true"
        />
        {children}
      </span>
    );
  }

  if (variant === 'outline') {
    return (
      <span
        className={[
          'inline-flex items-center justify-center',
          'rounded-full font-medium whitespace-nowrap',
          'border',
          sizeStyles[size],
          className,
        ].join(' ')}
        style={{
          borderColor: color || 'var(--color-border-strong)',
          color: color || 'var(--color-text-secondary)',
        }}
      >
        {children}
      </span>
    );
  }

  return (
    <span
      className={[
        'inline-flex items-center justify-center',
        'rounded-full font-medium whitespace-nowrap',
        sizeStyles[size],
        className,
      ].join(' ')}
      style={{
        backgroundColor: color ? `${color}18` : 'var(--color-border)',
        color: color || 'var(--color-text-secondary)',
      }}
    >
      {children}
    </span>
  );
}
