interface SkeletonProps {
  width?: string | number;
  height?: string | number;
  rounded?: 'sm' | 'md' | 'lg' | 'full';
  className?: string;
}

export default function Skeleton({
  width,
  height,
  rounded = 'sm',
  className = '',
}: SkeletonProps) {
  const roundedClass =
    rounded === 'sm' ? 'rounded-sm' :
    rounded === 'md' ? 'rounded-md' :
    rounded === 'lg' ? 'rounded-lg' :
    'rounded-full';

  return (
    <div
      className={`skeleton ${roundedClass} ${className}`}
      style={{
        width: typeof width === 'number' ? `${width}px` : width,
        height: typeof height === 'number' ? `${height}px` : height,
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
          className="skeleton rounded-sm"
          style={{
            height: '14px',
            width: i === lines - 1 ? '60%' : '100%',
          }}
        />
      ))}
    </div>
  );
}

export function SkeletonCard({ className = '' }: { className?: string }) {
  return (
    <div
      className={`flex gap-3 p-4 border border-border rounded-md ${className}`}
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
