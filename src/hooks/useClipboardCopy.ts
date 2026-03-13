'use client';

import { useCallback } from 'react';
import { useToast } from '@/components/ui/Toast';

export function useClipboardCopy() {
  const { addToast } = useToast();

  const copy = useCallback(
    async (text: string, successMessage = 'Skopiowano do schowka') => {
      try {
        await navigator.clipboard.writeText(text);
        addToast(successMessage, 'success');
        return true;
      } catch {
        addToast('Nie udało się skopiować do schowka', 'error');
        return false;
      }
    },
    [addToast],
  );

  return { copy };
}
