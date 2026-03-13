'use client';

import { useState, useRef, useCallback, useEffect, type ReactNode } from 'react';

interface BottomSheetProps {
  children: ReactNode;
  peekContent: ReactNode;
}

const COLLAPSED_HEIGHT = 60;
const EXPANDED_VH = 80;
const SNAP_THRESHOLD = 100;

export default function BottomSheet({ children, peekContent }: BottomSheetProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [translateY, setTranslateY] = useState(0);
  const dragStartRef = useRef(0);
  const currentTranslateRef = useRef(0);
  const sheetRef = useRef<HTMLDivElement>(null);

  const expandedOffset = 0;
  const collapsedOffset = typeof window !== 'undefined'
    ? window.innerHeight * (EXPANDED_VH / 100) - COLLAPSED_HEIGHT
    : 500;

  const baseOffset = isExpanded ? expandedOffset : collapsedOffset;

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
      // Dragging down from expanded
      if (diff > SNAP_THRESHOLD) {
        setIsExpanded(false);
      }
    } else {
      // Dragging up from collapsed
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

  // Prevent body scroll when expanded
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
          className="fixed inset-0 z-40 bg-black/30"
          onClick={handleOverlayClick}
          aria-hidden="true"
          style={{
            transition: isDragging ? 'none' : 'opacity 300ms ease-out',
          }}
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
        }}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      >
        {/* Drag handle + peek */}
        <button
          onClick={handleToggle}
          className="w-full flex flex-col items-center"
          style={{ height: `${COLLAPSED_HEIGHT}px` }}
          aria-label={isExpanded ? 'Zwiń koszyk' : 'Rozwiń koszyk'}
        >
          <div className="w-8 h-1 rounded-full bg-border-strong mt-2 mb-2" aria-hidden="true" />
          <div className="w-full px-4 flex-1 flex items-center">
            {peekContent}
          </div>
        </button>

        {/* Scrollable content */}
        <div
          className="overflow-y-auto px-4 pb-8"
          style={{ height: `calc(${EXPANDED_VH}vh - ${COLLAPSED_HEIGHT}px)` }}
        >
          {children}
        </div>
      </div>
    </>
  );
}
