import type { ReactNode } from 'react';
import { SearchX } from 'lucide-react';
import Button from '@/components/ui/Button';

interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  actionLabel?: string;
  onAction?: () => void;
  className?: string;
}

export default function EmptyState({
  icon,
  title,
  description,
  actionLabel,
  onAction,
  className = '',
}: EmptyStateProps) {
  return (
    <div
      className={`flex flex-col items-center justify-center py-12 px-6 text-center ${className}`}
    >
      <div
        className="mb-4 text-[var(--color-text-tertiary)]"
        aria-hidden="true"
      >
        {icon || <SearchX size={40} strokeWidth={1.5} />}
      </div>

      <p className="text-[var(--text-base)] font-medium text-[var(--color-text-primary)] mb-1">
        {title}
      </p>

      {description && (
        <p className="text-[var(--text-sm)] text-[var(--color-text-secondary)] max-w-xs">
          {description}
        </p>
      )}

      {actionLabel && onAction && (
        <div className="mt-4">
          <Button variant="outline" size="sm" onClick={onAction}>
            {actionLabel}
          </Button>
        </div>
      )}
    </div>
  );
}
