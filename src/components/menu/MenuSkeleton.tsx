import Skeleton from '@/components/ui/Skeleton';

export default function MenuSkeleton() {
  return (
    <div className="flex flex-col gap-6" aria-hidden="true">
      {/* Category tabs skeleton */}
      <div className="flex gap-2">
        <Skeleton width={64} height={32} rounded="full" />
        <Skeleton width={80} height={32} rounded="full" />
        <Skeleton width={56} height={32} rounded="full" />
      </div>

      {/* Category name */}
      <Skeleton width={100} height={12} />

      {/* Items */}
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="flex items-start gap-3 py-3">
          <div className="flex-1 flex flex-col gap-2">
            <Skeleton width="60%" height={16} />
            <Skeleton width="80%" height={12} />
            <div className="flex gap-4 mt-1">
              <Skeleton width={100} height={14} />
              <Skeleton width={100} height={14} />
              <Skeleton width={100} height={14} />
            </div>
          </div>
          <Skeleton width={32} height={32} rounded="sm" />
        </div>
      ))}
    </div>
  );
}
