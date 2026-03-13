'use client';

import { useEffect, useRef, useState } from 'react';
import { formatPrice } from '@/lib/format';

interface AnimatedPriceProps {
  valueGrosz: number;
  className?: string;
}

export default function AnimatedPrice({ valueGrosz, className = '' }: AnimatedPriceProps) {
  const [displayValue, setDisplayValue] = useState(valueGrosz);
  const [isFlashing, setIsFlashing] = useState(false);
  const prevValueRef = useRef(valueGrosz);
  const frameRef = useRef<number>(0);

  useEffect(() => {
    const prevValue = prevValueRef.current;
    prevValueRef.current = valueGrosz;

    if (prevValue === valueGrosz) return;

    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (prefersReducedMotion) {
      setDisplayValue(valueGrosz);
      return;
    }

    // Trigger flash
    setIsFlashing(true);
    const flashTimer = setTimeout(() => setIsFlashing(false), 800);

    // Animate counter
    const start = performance.now();
    const duration = 300;
    const from = prevValue;
    const to = valueGrosz;

    const animate = (now: number) => {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - (1 - progress) * (1 - progress);
      const current = Math.round(from + (to - from) * eased);
      setDisplayValue(current);

      if (progress < 1) {
        frameRef.current = requestAnimationFrame(animate);
      }
    };

    frameRef.current = requestAnimationFrame(animate);

    return () => {
      cancelAnimationFrame(frameRef.current);
      clearTimeout(flashTimer);
    };
  }, [valueGrosz]);

  return (
    <span
      className={[
        'tabular-nums transition-colors',
        isFlashing ? 'animate-price-flash rounded-sm px-1 -mx-1' : '',
        className,
      ].join(' ')}
    >
      {formatPrice(displayValue)}
    </span>
  );
}
