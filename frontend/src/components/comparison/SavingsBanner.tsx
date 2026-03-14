'use client';

import { PiggyBank } from 'lucide-react';
import { useComparisonStore } from '@/stores/comparison';

export default function SavingsBanner() {
  const comparisonReady = useComparisonStore((s) => s.comparisonReady);
  const savingsDisplay = useComparisonStore((s) => s.savingsDisplay);
  const savingsGrosze = useComparisonStore((s) => s.savingsGrosze);

  if (!comparisonReady || savingsGrosze <= 0 || !savingsDisplay) return null;

  return (
    <div
      className="flex items-center gap-3 p-3 rounded-md border border-savings-border bg-savings-bg animate-savings-in"
      aria-live="polite"
      role="status"
    >
      <PiggyBank size={20} className="shrink-0 text-savings-text" aria-hidden="true" />
      <p className="text-sm font-semibold text-savings-text">
        {savingsDisplay}
      </p>

      <style jsx>{`
        @keyframes savings-in {
          0% {
            opacity: 0;
            transform: translateY(12px);
          }
          60% {
            transform: translateY(-2px);
          }
          100% {
            opacity: 1;
            transform: translateY(0);
          }
        }
        .animate-savings-in {
          animation: savings-in 400ms cubic-bezier(0.32, 0.72, 0, 1) both;
        }
        @media (prefers-reduced-motion: reduce) {
          .animate-savings-in {
            animation: none;
          }
        }
      `}</style>
    </div>
  );
}
