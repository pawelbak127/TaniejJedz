import type { Platform } from '@/generated/api-types';

export interface PlatformMeta {
  name: string;
  shortName: string;
  color: string;
  cssVar: string;
}

export const PLATFORMS: Record<Platform, PlatformMeta> = {
  pyszne: {
    name: 'Pyszne.pl',
    shortName: 'Pyszne',
    color: '#FF8000',
    cssVar: 'var(--color-pyszne)',
  },
  wolt: {
    name: 'Wolt',
    shortName: 'Wolt',
    color: '#009DE0',
    cssVar: 'var(--color-wolt)',
  },
  ubereats: {
    name: 'Uber Eats',
    shortName: 'UberEats',
    color: '#06C167',
    cssVar: 'var(--color-ubereats)',
  },
  glovo: {
    name: 'Glovo',
    shortName: 'Glovo',
    color: '#FFC244',
    cssVar: 'var(--color-glovo)',
  },
} as const;

export const PLATFORM_ORDER: Platform[] = ['pyszne', 'wolt', 'ubereats', 'glovo'];

export function getPlatformMeta(platform: Platform): PlatformMeta {
  return PLATFORMS[platform];
}

export function getPlatformName(platform: Platform): string {
  return PLATFORMS[platform].name;
}

export function getPlatformColor(platform: Platform): string {
  return PLATFORMS[platform].color;
}
