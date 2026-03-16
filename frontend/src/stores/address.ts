'use client';

import { create } from 'zustand';
import type { Address } from '@/generated/api-types';

interface AddressState {
  address: Address | null;
  setAddress: (address: Address) => void;
  clearAddress: () => void;
}

export const useAddressStore = create<AddressState>((set) => ({
  address: null,
  setAddress: (address) => set({ address }),
  clearAddress: () => set({ address: null }),
}));
