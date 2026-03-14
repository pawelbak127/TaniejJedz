import type { Platform } from '@/generated/api-types';
import { getPlatformMeta } from '@/lib/platforms';

interface PlatformIconProps {
  platform: Platform;
  showLabel?: boolean;
  size?: 'sm' | 'md';
  className?: string;
}

export default function PlatformIcon({
  platform,
  showLabel = true,
  size = 'sm',
  className = '',
}: PlatformIconProps) {
  const meta = getPlatformMeta(platform);
  const dotSize = size === 'sm' ? 'w-2 h-2' : 'w-2.5 h-2.5';

  return (
    <span className={`inline-flex items-center gap-1.5 ${className}`}>
      <span
        className={`${dotSize} rounded-full shrink-0`}
        style={{ backgroundColor: meta.color }}
        aria-hidden="true"
      />
      {showLabel && (
        <span className="text-xs font-medium text-text-secondary">
          {meta.shortName}
        </span>
      )}
    </span>
  );
}
