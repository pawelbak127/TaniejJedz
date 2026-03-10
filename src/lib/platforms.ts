export type Platform = "pyszne" | "ubereats" | "wolt" | "glovo";

export interface PlatformMeta {
  name: string;
  shortName: string;
  color: string;
}

export const PLATFORMS: Record<Platform, PlatformMeta> = {
  pyszne: { 
    name: "Pyszne.pl", 
    shortName: "Pyszne", 
    color: "var(--color-pyszne)" 
  },
  wolt: { 
    name: "Wolt", 
    shortName: "Wolt", 
    color: "var(--color-wolt)" 
  },
  ubereats: { 
    name: "Uber Eats", 
    shortName: "UberEats", 
    color: "var(--color-ubereats)" 
  },
  glovo: { 
    name: "Glovo", 
    shortName: "Glovo", 
    color: "var(--color-glovo)" 
  },
} as const;

export const SUPPORTED_PLATFORMS: Platform[] = ["pyszne", "wolt", "ubereats", "glovo"];