'use client';

import { useEffect, useRef, useCallback, useState } from 'react';
import { useComparisonStore } from '@/stores/comparison';
import { SSE_MAX_RETRIES, SSE_TIMEOUT_MS } from '@/lib/constants';
import { PLATFORM_ORDER } from '@/lib/platforms';

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
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [sseError, setSseError] = useState(false);

  const setPlatformResult = useComparisonStore((s) => s.setPlatformResult);
  const setComparisonResult = useComparisonStore((s) => s.setComparisonResult);

  const cleanup = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
  }, []);

  // Mark all still-fetching platforms as errored
  const markFetchingAsError = useCallback(() => {
    const store = useComparisonStore.getState();
    for (const platform of PLATFORM_ORDER) {
      const status = store.platformStatus.get(platform);
      if (status === 'fetching' || status === 'idle') {
        setPlatformResult(platform, 'error');
      }
    }
  }, [setPlatformResult]);

  const connect = useCallback(() => {
    if (!comparisonId) return;

    cleanup();
    retryCountRef.current = 0;
    setSseError(false);

    const scenarioParam = getScenarioParam();
    const url = `/api/v1/compare/stream?id=${comparisonId}${scenarioParam}`;

    const es = new EventSource(url);
    eventSourceRef.current = es;

    // Global safety timeout
    const startGlobalTimeout = () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      timeoutRef.current = setTimeout(() => {
        console.warn('[SSE] Timeout reached, closing connection');
        cleanup();
        markFetchingAsError();

        const { comparisonReady } = useComparisonStore.getState();
        if (!comparisonReady) {
          setComparisonResult(null, 0, '');
        }
      }, SSE_TIMEOUT_MS);
    };

    startGlobalTimeout();

    es.addEventListener('platform_status', (e: MessageEvent) => {
      // Reset timeout on each event — stream is alive
      startGlobalTimeout();
      try {
        const data = JSON.parse(e.data);
        setPlatformResult(data.platform, data.status, data.data);
      } catch (err) {
        console.warn('[SSE] Failed to parse platform_status event:', err);
      }
    });

    es.addEventListener('comparison_ready', (e: MessageEvent) => {
      cleanup();
      try {
        const data = JSON.parse(e.data);
        setComparisonResult(data.cheapest_open, data.savings_grosz, data.savings_display);
      } catch (err) {
        console.warn('[SSE] Failed to parse comparison_ready event:', err);
      }
    });

    es.addEventListener('timeout', () => {
      cleanup();
      markFetchingAsError();
      setComparisonResult(null, 0, '');
    });

    es.onerror = () => {
      retryCountRef.current += 1;
      console.warn(`[SSE] Connection error #${retryCountRef.current}/${SSE_MAX_RETRIES}`);

      if (retryCountRef.current >= SSE_MAX_RETRIES) {
        console.warn('[SSE] Max retries reached, giving up');
        cleanup();
        markFetchingAsError();
        setSseError(true);
      }
      // Otherwise EventSource auto-reconnects
    };
  }, [comparisonId, setPlatformResult, setComparisonResult, cleanup, markFetchingAsError]);

  useEffect(() => {
    connect();
    return cleanup;
  }, [connect, cleanup]);

  const retrySSE = useCallback(() => {
    setSseError(false);
    connect();
  }, [connect]);

  return { sseError, retrySSE };
}
