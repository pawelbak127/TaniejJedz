'use client';

import { useEffect, useCallback } from 'react';
import { useAddressStore } from '@/stores/address';
import type { Address } from '@/generated/api-types';

const STORAGE_KEY = 'taniejjedz_address';

function readFromStorage(): Address | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as Address;
  } catch {
    return null;
  }
}

function writeToStorage(address: Address | null): void {
  if (typeof window === 'undefined') return;
  try {
    if (address) {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(address));
    } else {
      sessionStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    // sessionStorage full or unavailable
  }
}

export function useAddress() {
  const address = useAddressStore((s) => s.address);
  const setAddress = useAddressStore((s) => s.setAddress);
  const clearAddress = useAddressStore((s) => s.clearAddress);

  // Hydrate from sessionStorage on mount
  useEffect(() => {
    const stored = readFromStorage();
    if (stored && !address) {
      setAddress(stored);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const saveAddress = useCallback(
    (newAddress: Address) => {
      setAddress(newAddress);
      writeToStorage(newAddress);
    },
    [setAddress],
  );

  const removeAddress = useCallback(() => {
    clearAddress();
    writeToStorage(null);
  }, [clearAddress]);

  return {
    address,
    saveAddress,
    removeAddress,
  };
}
