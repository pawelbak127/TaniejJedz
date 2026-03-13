'use client';

import { Check, AlertTriangle, X } from 'lucide-react';
import { useComparisonStore } from '@/stores/comparison';
import { PLATFORM_ORDER, getPlatformMeta } from '@/lib/platforms';
import type { Platform } from '@/generated/api-types';

type PlatformStatus = 'idle' | 'fetching' | 'ready' | 'cached' | 'timeout' | 'closed' | 'error';

function StatusDot({ platform, status }: { platform: Platform; status: PlatformStatus }) {
  const meta = getPlatformMeta(platform);

  switch (status) {
    case 'fetching':
      return (
        <span
          className="w-2.5 h-2.5 rounded-full shrink-0 animate-pulse"
          style={{ backgroundColor: meta.color }}
          aria-hidden="true"
        />
      );
    case 'ready':
    case 'cached':
      return (
        <span
          className="w-2.5 h-2.5 rounded-full shrink-0"
          style={{ backgroundColor: meta.color }}
          aria-hidden="true"
        />
      );
    case 'timeout':
      return (
        <span className="w-2.5 h-2.5 rounded-full shrink-0 bg-warning" aria-hidden="true" />
      );
    case 'error':
      return (
        <span className="w-2.5 h-2.5 rounded-full shrink-0 bg-danger" aria-hidden="true" />
      );
    case 'closed':
      return (
        <span
          className="w-2.5 h-2.5 rounded-full shrink-0 border-[1.5px] border-border-strong"
          aria-hidden="true"
        />
      );
    default: // idle
      return (
        <span className="w-2.5 h-2.5 rounded-full shrink-0 bg-border" aria-hidden="true" />
      );
  }
}

function StatusIcon({ status }: { status: PlatformStatus }) {
  switch (status) {
    case 'ready':
    case 'cached':
      return <Check size={11} className="text-fresh" />;
    case 'timeout':
      return <AlertTriangle size={11} className="text-warning" />;
    case 'error':
      return <X size={11} className="text-danger" />;
    default:
      return null;
  }
}

function statusLabel(status: PlatformStatus, ageSeconds?: number, nextOpen?: string): string {
  switch (status) {
    case 'idle': return '';
    case 'fetching': return 'sprawdzam...';
    case 'ready': return 'sprawdzono';
    case 'cached': return ageSeconds ? `sprzed ${Math.round(ageSeconds / 60)} min` : 'z cache';
    case 'timeout': return 'przekroczono limit czasu';
    case 'closed': return nextOpen ? `zamknięte (otwiera: ${nextOpen})` : 'zamknięte';
    case 'error': return 'błąd';
  }
}

export default function PlatformStatusBar() {
  const platformStatus = useComparisonStore((s) => s.platformStatus);
  const comparisonId = useComparisonStore((s) => s.comparisonId);

  if (!comparisonId) return null;

  return (
    <div
      className="flex flex-wrap gap-x-4 gap-y-2 p-3 rounded-md border border-border bg-surface"
      aria-live="polite"
      aria-label="Status sprawdzania platform"
    >
      {PLATFORM_ORDER.map((platform) => {
        const status = platformStatus.get(platform) || 'idle';
        const meta = getPlatformMeta(platform);
        const label = statusLabel(status);

        return (
          <div key={platform} className="flex items-center gap-1.5">
            <StatusDot platform={platform} status={status} />
            <span className="text-xs font-medium text-text-secondary">
              {meta.shortName}
            </span>
            <StatusIcon status={status} />
            {label && (
              <span className="text-xs text-text-tertiary">
                {label}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
