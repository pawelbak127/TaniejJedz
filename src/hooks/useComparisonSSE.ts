'use client';

import { useEffect, useRef, useCallback, useState } from 'react';
import { useComparisonStore } from '@/stores/comparison';
import { SSE_MAX_RETRIES } from '@/lib/constants';

interface SSEState {
  sseError: boolean;
  retrySSE: () => void;
}

function getScenarioParam(): string {
  if (typeof window === 'undefined') return '';
  const params = new URLSearchParams(window.location.search);
  const scenario = params.get('scenario');
  return scenario ? `&scenario=${scenario}` : '';
}

export function useComparisonSSE(comparisonId: string | null): SSEState {
  const eventSourceRef = useRef<EventSource | null>(null);
  const retryCountRef = useRef(0);
  const [sseError, setSseError] = useState(false);

  const setPlatformResult = useComparisonStore((s) => s.setPlatformResult);
  const setComparisonResult = useComparisonStore((s) => s.setComparisonResult);

  const connect = useCallback(() => {
    if (!comparisonId) return;

    eventSourceRef.current?.close();
    retryCountRef.current = 0;
    setSseError(false);

    // Dev: read ?scenario= from page URL and forward to SSE endpoint
    const scenarioParam = getScenarioParam();
    const url = `/api/v1/compare/stream?id=${comparisonId}${scenarioParam}`;

    const es = new EventSource(url);
    eventSourceRef.current = es;

    es.addEventListener('platform_status', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        setPlatformResult(data.platform, data.status, data.data);
      } catch (err) {
        console.warn('[SSE] Failed to parse platform_status event:', err);
      }
    });

    es.addEventListener('comparison_ready', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        setComparisonResult(data.cheapest_open, data.savings_grosz, data.savings_display);
      } catch (err) {
        console.warn('[SSE] Failed to parse comparison_ready event:', err);
      }
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
        setSseError(true);
      }
    };
  }, [comparisonId, setPlatformResult, setComparisonResult]);

  useEffect(() => {
    connect();
    return () => {
      eventSourceRef.current?.close();
    };
  }, [connect]);

  const retrySSE = useCallback(() => {
    connect();
  }, [connect]);

  return { sseError, retrySSE };
}
