import type { Platform, PlatformAvailability } from '@/generated/api-types';
import { PLATFORM_ORDER, getPlatformMeta } from '@/lib/platforms';

interface PlatformBadgesProps {
  platforms: Partial<Record<Platform, PlatformAvailability>>;
  showRating?: boolean;
  size?: 'sm' | 'md';
}

export default function PlatformBadges({
  platforms,
  showRating = false,
  size = 'sm',
}: PlatformBadgesProps) {
  const dotSize = size === 'sm' ? 'w-2 h-2' : 'w-2.5 h-2.5';

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
      {PLATFORM_ORDER.map((key) => {
        const meta = getPlatformMeta(key);
        const info = platforms[key];
        const isAvailable = info?.available ?? false;
        const isOpen = info?.is_open ?? false;

        return (
          <span
            key={key}
            className="inline-flex items-center gap-1.5 text-[var(--text-xs)] font-medium"
            style={{
              color: isAvailable
                ? isOpen
                  ? 'var(--color-text-secondary)'
                  : 'var(--color-text-tertiary)'
                : 'var(--color-text-tertiary)',
            }}
          >
            <span
              className={`${dotSize} rounded-full shrink-0`}
              style={
                isAvailable
                  ? { backgroundColor: meta.color }
                  : { border: `1.5px solid var(--color-border-strong)` }
              }
              aria-hidden="true"
            />
            <span className={!isAvailable || !isOpen ? 'opacity-60' : ''}>
              {meta.shortName}
            </span>
            {showRating && info?.rating && isAvailable && (
              <span className="text-[var(--color-text-tertiary)]">
                ({info.rating.toFixed(1)})
              </span>
            )}
          </span>
        );
      })}
    </div>
  );
}
