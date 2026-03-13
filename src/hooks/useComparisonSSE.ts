'use client';

import { useEffect, useRef, useCallback } from 'react';
import { useComparisonStore } from '@/stores/comparison';
import { SSE_MAX_RETRIES } from '@/lib/constants';

export function useComparisonSSE(comparisonId: string | null) {
  const eventSourceRef = useRef<EventSource | null>(null);
  const retryCountRef = useRef(0);

  const setPlatformResult = useComparisonStore((s) => s.setPlatformResult);
  const setComparisonResult = useComparisonStore((s) => s.setComparisonResult);

  const connect = useCallback(() => {
    if (!comparisonId) return;

    eventSourceRef.current?.close();
    retryCountRef.current = 0;

    const es = new EventSource(`/api/v1/compare/stream?id=${comparisonId}`);
    eventSourceRef.current = es;

    es.addEventListener('platform_status', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      setPlatformResult(data.platform, data.status, data.data);
    });

    es.addEventListener('comparison_ready', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      setComparisonResult(data.cheapest_open, data.savings_grosz, data.savings_display);
      es.close();
    });

    es.addEventListener('timeout', () => {
      setComparisonResult(null, 0, '');
      es.close();
    });

    es.onerror = () => {
      retryCountRef.current += 1;
      if (retryCountRef.current >= SSE_MAX_RETRIES) {
        es.close();
      }
    };
  }, [comparisonId, setPlatformResult, setComparisonResult]);

  useEffect(() => {
    connect();
    return () => {
      eventSourceRef.current?.close();
    };
  }, [connect]);
}
