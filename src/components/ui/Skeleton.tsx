interface SkeletonProps {
  width?: string | number;
  height?: string | number;
  rounded?: 'sm' | 'md' | 'lg' | 'full';
  className?: string;
}

const roundedMap: Record<string, string> = {
  sm: 'var(--radius-sm)',
  md: 'var(--radius-md)',
  lg: 'var(--radius-lg)',
  full: 'var(--radius-full)',
};

export default function Skeleton({
  width,
  height,
  rounded = 'sm',
  className = '',
}: SkeletonProps) {
  return (
    <div
      className={`skeleton ${className}`}
      style={{
        width: typeof width === 'number' ? `${width}px` : width,
        height: typeof height === 'number' ? `${height}px` : height,
        borderRadius: roundedMap[rounded],
      }}
      aria-hidden="true"
    />
  );
}

export function SkeletonText({
  lines = 3,
  className = '',
}: {
  lines?: number;
  className?: string;
}) {
  return (
    <div className={`flex flex-col gap-2 ${className}`} aria-hidden="true">
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className="skeleton"
          style={{
            height: '14px',
            width: i === lines - 1 ? '60%' : '100%',
            borderRadius: 'var(--radius-sm)',
          }}
        />
      ))}
    </div>
  );
}

export function SkeletonCard({ className = '' }: { className?: string }) {
  return (
    <div
      className={`flex gap-3 p-4 border border-[var(--color-border)] rounded-[var(--radius-md)] ${className}`}
      aria-hidden="true"
    >
      <Skeleton width={80} height={80} rounded="sm" />
      <div className="flex-1 flex flex-col gap-2">
        <Skeleton height={18} width="70%" />
        <Skeleton height={14} width="50%" />
        <div className="flex gap-2 mt-1">
          <Skeleton width={48} height={20} rounded="full" />
          <Skeleton width={48} height={20} rounded="full" />
          <Skeleton width={48} height={20} rounded="full" />
        </div>
        <Skeleton height={14} width="40%" />
      </div>
    </div>
  );
}

export function SkeletonPrice({ className = '' }: { className?: string }) {
  return (
    <Skeleton
      width={72}
      height={20}
      rounded="sm"
      className={className}
    />
  );
}
