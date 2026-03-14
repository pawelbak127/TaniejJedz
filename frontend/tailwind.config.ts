import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: "var(--color-primary)",
          hover: "var(--color-primary-hover)",
          light: "var(--color-primary-light)",
        },
        accent: {
          DEFAULT: "var(--color-accent)",
          dark: "var(--color-accent-dark)",
        },
        danger: "var(--color-danger)",
        warning: "var(--color-warning)",
        surface: {
          DEFAULT: "var(--color-surface)",
          raised: "var(--color-surface-raised)",
        },
        border: {
          DEFAULT: "var(--color-border)",
          strong: "var(--color-border-strong)",
        },
        text: {
          primary: "var(--color-text-primary)",
          secondary: "var(--color-text-secondary)",
          tertiary: "var(--color-text-tertiary)",
          inverse: "var(--color-text-inverse)",
        },
        savings: {
          bg: "var(--color-savings-bg)",
          text: "var(--color-savings-text)",
          border: "var(--color-savings-border)",
        },
        platform: {
          pyszne: "var(--color-pyszne)",
          ubereats: "var(--color-ubereats)",
          wolt: "var(--color-wolt)",
          glovo: "var(--color-glovo)",
        },
        fresh: "var(--color-fresh)",
        "stale-mild": "var(--color-stale-mild)",
        "stale-severe": "var(--color-stale-severe)",
        bg: "var(--color-bg)",
      },
      borderRadius: {
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
        xl: "var(--radius-xl)",
      },
      boxShadow: {
        sm: "var(--shadow-sm)",
        md: "var(--shadow-md)",
        lg: "var(--shadow-lg)",
        xl: "var(--shadow-xl)",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "-apple-system", "sans-serif"],
        mono: ["var(--font-mono)"],
      },
      fontSize: {
        xs: "var(--text-xs)",
        sm: "var(--text-sm)",
        base: "var(--text-base)",
        lg: "var(--text-lg)",
        xl: "var(--text-xl)",
        "2xl": "var(--text-2xl)",
        "3xl": "var(--text-3xl)",
      },
      maxWidth: {
        container: "1280px",
      },
      transitionDuration: {
        fast: "120ms",
        base: "200ms",
        slow: "350ms",
      },
    },
  },
  plugins: [],
};
export default config;
