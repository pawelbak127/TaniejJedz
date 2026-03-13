'use client';

import { create } from 'zustand';
import type {
  Platform,
  Address,
  PlatformComparisonResult,
} from '@/generated/api-types';

type PlatformStatus = 'idle' | 'fetching' | 'ready' | 'cached' | 'timeout' | 'closed' | 'error';

export interface CartItemState {
  canonicalItemId: string;
  name: string;
  quantity: number;
  selectedModifiers: Partial<Record<Platform, string[]>>;
  basePrices: Partial<Record<Platform, number>>;
}

interface ComparisonState {
  // === Address ===
  address: Address | null;

  // === Cart ===
  items: Map<string, CartItemState>;

  // === Comparison (populated by SSE) ===
  comparisonId: string | null;
  platformStatus: Map<Platform, PlatformStatus>;
  platformResults: Map<Platform, PlatformComparisonResult>;
  comparisonReady: boolean;
  cheapestPlatform: Platform | null;
  savingsGrosze: number;
  savingsDisplay: string;
}

interface ComparisonActions {
  // Address
  setAddress: (address: Address) => void;
  clearAddress: () => void;

  // Cart
  addItem: (item: CartItemState) => void;
  removeItem: (itemId: string) => void;
  updateQuantity: (itemId: string, quantity: number) => void;
  updateModifiers: (itemId: string, platform: Platform, optionIds: string[]) => void;
  clearCart: () => void;
  itemCount: () => number;

  // Comparison
  setComparisonId: (id: string) => void;
  setPlatformResult: (platform: Platform, status: string, result?: PlatformComparisonResult) => void;
  setComparisonResult: (cheapest: Platform | null, savings: number, display: string) => void;
  resetComparison: () => void;

  // Derived
  estimatedSubtotal: (platform: Platform) => number;
  openPlatforms: () => Platform[];
}

type ComparisonStore = ComparisonState & ComparisonActions;

export const useComparisonStore = create<ComparisonStore>((set, get) => ({
  // === State ===
  address: null,
  items: new Map(),
  comparisonId: null,
  platformStatus: new Map(),
  platformResults: new Map(),
  comparisonReady: false,
  cheapestPlatform: null,
  savingsGrosze: 0,
  savingsDisplay: '',

  // === Address ===
  setAddress: (address) => set({ address }),
  clearAddress: () => set({ address: null }),

  // === Cart ===
  addItem: (item) =>
    set((state) => {
      const next = new Map(state.items);
      const existing = next.get(item.canonicalItemId);
      if (existing) {
        next.set(item.canonicalItemId, {
          ...existing,
          quantity: existing.quantity + item.quantity,
          selectedModifiers: {
            ...existing.selectedModifiers,
            ...item.selectedModifiers,
          },
        });
      } else {
        next.set(item.canonicalItemId, item);
      }
      return { items: next };
    }),

  removeItem: (itemId) =>
    set((state) => {
      const next = new Map(state.items);
      next.delete(itemId);
      return { items: next };
    }),

  updateQuantity: (itemId, quantity) =>
    set((state) => {
      const next = new Map(state.items);
      const item = next.get(itemId);
      if (!item) return state;
      if (quantity <= 0) {
        next.delete(itemId);
      } else {
        next.set(itemId, { ...item, quantity });
      }
      return { items: next };
    }),

  updateModifiers: (itemId, platform, optionIds) =>
    set((state) => {
      const next = new Map(state.items);
      const item = next.get(itemId);
      if (!item) return state;
      next.set(itemId, {
        ...item,
        selectedModifiers: {
          ...item.selectedModifiers,
          [platform]: optionIds,
        },
      });
      return { items: next };
    }),

  clearCart: () =>
    set({
      items: new Map(),
      comparisonId: null,
      platformStatus: new Map(),
      platformResults: new Map(),
      comparisonReady: false,
      cheapestPlatform: null,
      savingsGrosze: 0,
      savingsDisplay: '',
    }),

  itemCount: () => {
    let count = 0;
    get().items.forEach((item) => {
      count += item.quantity;
    });
    return count;
  },

  // === Comparison ===
  setComparisonId: (id) =>
    set({
      comparisonId: id,
      comparisonReady: false,
      cheapestPlatform: null,
      savingsGrosze: 0,
      savingsDisplay: '',
    }),

  setPlatformResult: (platform, status, result) =>
    set((state) => {
      const nextStatus = new Map(state.platformStatus);
      nextStatus.set(platform, status as PlatformStatus);

      const nextResults = new Map(state.platformResults);
      if (result) {
        nextResults.set(platform, result);
      }

      return {
        platformStatus: nextStatus,
        platformResults: nextResults,
      };
    }),

  setComparisonResult: (cheapest, savings, display) =>
    set({
      comparisonReady: true,
      cheapestPlatform: cheapest,
      savingsGrosze: savings,
      savingsDisplay: display,
    }),

  resetComparison: () =>
    set({
      comparisonId: null,
      platformStatus: new Map(),
      platformResults: new Map(),
      comparisonReady: false,
      cheapestPlatform: null,
      savingsGrosze: 0,
      savingsDisplay: '',
    }),

  // === Derived ===
  estimatedSubtotal: (platform) => {
    let total = 0;
    get().items.forEach((item) => {
      const basePrice = item.basePrices[platform];
      if (basePrice !== undefined) {
        total += basePrice * item.quantity;
      }
    });
    return total;
  },

  openPlatforms: () => {
    const platforms: Platform[] = [];
    get().platformResults.forEach((result, platform) => {
      if (result.is_open) {
        platforms.push(platform);
      }
    });
    return platforms;
  },
}));
