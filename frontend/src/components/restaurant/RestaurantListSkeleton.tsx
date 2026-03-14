import { SkeletonCard } from '@/components/ui/Skeleton';

interface RestaurantListSkeletonProps {
  count?: number;
}

export default function RestaurantListSkeleton({ count = 6 }: RestaurantListSkeletonProps) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  );
}
