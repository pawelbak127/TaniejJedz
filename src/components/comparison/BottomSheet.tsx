'use client';

import { useState, useRef, useCallback, useEffect, type ReactNode } from 'react';

interface BottomSheetProps {
  children: ReactNode;
  peekContent: ReactNode;
}

const COLLAPSED_HEIGHT = 60;
const EXPANDED_VH = 80;
const SNAP_THRESHOLD = 80;

export default function BottomSheet({ children, peekContent }: BottomSheetProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [translateY, setTranslateY] = useState(0);
  const dragStartRef = useRef(0);
  const currentTranslateRef = useRef(0);
  const sheetRef = useRef<HTMLDivElement>(null);

  const getCollapsedOffset = useCallback(() => {
    if (typeof window === 'undefined') return 500;
    return window.innerHeight * (EXPANDED_VH / 100) - COLLAPSED_HEIGHT;
  }, []);

  const baseOffset = isExpanded ? 0 : getCollapsedOffset();

  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    setIsDragging(true);
    dragStartRef.current = e.touches[0].clientY;
    currentTranslateRef.current = 0;
  }, []);

  const handleTouchMove = useCallback((e: React.TouchEvent) => {
    if (!isDragging) return;
    const diff = e.touches[0].clientY - dragStartRef.current;
    currentTranslateRef.current = diff;
    setTranslateY(Math.max(0, diff));
  }, [isDragging]);

  const handleTouchEnd = useCallback(() => {
    setIsDragging(false);
    const diff = currentTranslateRef.current;

    if (isExpanded) {
      if (diff > SNAP_THRESHOLD) {
        setIsExpanded(false);
      }
    } else {
      if (diff < -SNAP_THRESHOLD) {
        setIsExpanded(true);
      }
    }

    setTranslateY(0);
  }, [isExpanded]);

  const handleToggle = useCallback(() => {
    setIsExpanded((prev) => !prev);
  }, []);

  const handleOverlayClick = useCallback(() => {
    setIsExpanded(false);
  }, []);

  useEffect(() => {
    if (isExpanded) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [isExpanded]);

  return (
    <>
      {/* Backdrop */}
      {isExpanded && (
        <div
          className="fixed inset-0 z-40 bg-black/30 transition-opacity"
          onClick={handleOverlayClick}
          aria-hidden="true"
        />
      )}

      {/* Sheet */}
      <div
        ref={sheetRef}
        className="fixed bottom-0 left-0 right-0 z-50 bg-surface border-t border-border rounded-t-lg shadow-xl"
        style={{
          height: `${EXPANDED_VH}vh`,
          transform: `translateY(calc(${baseOffset}px + ${isDragging ? translateY : 0}px))`,
          transition: isDragging ? 'none' : 'transform 300ms cubic-bezier(0.32, 0.72, 0, 1)',
          touchAction: 'none',
        }}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      >
        {/* Drag handle + peek */}
        <button
          onClick={handleToggle}
          className="w-full flex flex-col items-center touch-target"
          style={{ height: `${COLLAPSED_HEIGHT}px`, minHeight: '44px' }}
          aria-label={isExpanded ? 'Zwiń koszyk' : 'Rozwiń koszyk'}
        >
          <div className="w-8 h-1 rounded-full bg-border-strong mt-2 mb-2" aria-hidden="true" />
          <div className="w-full px-4 flex-1 flex items-center">
            {peekContent}
          </div>
        </button>

        {/* Scrollable content */}
        <div
          className="overflow-y-auto overscroll-contain px-4 pb-8"
          style={{
            height: `calc(${EXPANDED_VH}vh - ${COLLAPSED_HEIGHT}px)`,
            touchAction: 'pan-y',
          }}
        >
          {children}
        </div>
      </div>
    </>
  );
}
