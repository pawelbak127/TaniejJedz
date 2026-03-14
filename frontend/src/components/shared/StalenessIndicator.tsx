import { STALENESS_THRESHOLDS } from '@/lib/constants';

interface StalenessIndicatorProps {
  lastChecked: string;
  className?: string;
}

function getStaleness(lastChecked: string): 'fresh' | 'mild' | 'severe' {
  const ageSeconds = (Date.now() - new Date(lastChecked).getTime()) / 1000;
  if (ageSeconds < STALENESS_THRESHOLDS.fresh) return 'fresh';
  if (ageSeconds < STALENESS_THRESHOLDS.mild) return 'mild';
  return 'severe';
}

function formatAge(lastChecked: string): string {
  const ageSeconds = Math.round((Date.now() - new Date(lastChecked).getTime()) / 1000);
  if (ageSeconds < 60) return 'teraz';
  const minutes = Math.round(ageSeconds / 60);
  if (minutes < 60) return `${minutes} min temu`;
  const hours = Math.round(minutes / 60);
  return `${hours} godz. temu`;
}

const dotColorMap = {
  fresh: 'bg-fresh',
  mild: 'bg-stale-mild',
  severe: 'bg-stale-severe',
};

export default function StalenessIndicator({
  lastChecked,
  className = '',
}: StalenessIndicatorProps) {
  const staleness = getStaleness(lastChecked);
  const age = formatAge(lastChecked);

  return (
    <span className={`inline-flex items-center gap-1 text-xs text-text-tertiary ${className}`}>
      <span
        className={`w-1.5 h-1.5 rounded-full shrink-0 ${dotColorMap[staleness]}`}
        aria-hidden="true"
      />
      {age}
    </span>
  );
}
