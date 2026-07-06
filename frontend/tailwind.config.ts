import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      // Renkler tek kaynaktan (globals.css :root) türer; utility'ler var()'ten okur.
      // Değerler burada tanımlı DEĞİL — palet migration'ı (P1.2/b) yalnız :root'ta yapılır.
      colors: {
        bg: {
          primary: 'var(--bg-primary)',
          secondary: 'var(--bg-secondary)',
          tertiary: 'var(--bg-tertiary)',
          glass: 'var(--bg-glass)',
          'glass-light': 'var(--bg-glass-light)',
        },
        // ── Design Standards v1.3 owned yüzey merdiveni (Bible §01 COL-01/02) ──
        e: { 0: 'var(--e0)', 1: 'var(--e1)', 2: 'var(--e2)', 3: 'var(--e3)' },
        signal: {
          'strong-buy': 'var(--signal-strong-buy)',
          buy: 'var(--signal-buy)',
          hold: 'var(--signal-hold)',
          sell: 'var(--signal-sell)',
          'strong-sell': 'var(--signal-strong-sell)',
        },
        accent: {
          DEFAULT: 'var(--accent)',      // owned-blue — YALNIZ dolgu
          ui: 'var(--accent-ui)',        // a11y-türevi — 1px-UI/focus/border/nav
          hover: 'var(--accent-hover)',  // YALNIZ CTA-dolgu hover
          primary: 'var(--accent-primary)',           // EMEKLİ → accent (P1-F/c)
          secondary: 'var(--accent-secondary)',       // EMEKLİ → cyan
          glow: 'var(--accent-glow)',                 // EMEKLİ — P2 util-göç
          'glow-strong': 'var(--accent-glow-strong)', // EMEKLİ — P2
        },
        // ── owned semantik + AI-izi (Bible §01 COL-04..08) ──
        bull: 'var(--bull)',
        bear: 'var(--bear)',
        cyan: 'var(--cyan)',
        amber: 'var(--amber)',
        tx: { DEFAULT: 'var(--tx)', 2: 'var(--tx2)', 3: 'var(--tx3)' },
        text: {
          primary: 'var(--text-primary)',
          secondary: 'var(--text-secondary)',
          muted: 'var(--text-muted)',
          dark: 'var(--text-dark)',   // EMEKLİ (COL-03 4. ton yasak) — P2
        },
        border: {
          subtle: 'var(--border-subtle)',
          medium: 'var(--border-medium)',  // EMEKLİ → hl16 (P1-F/d)
          hl10: 'var(--hl10)', hl12: 'var(--hl12)', hl16: 'var(--hl16)', hl22: 'var(--hl22)',
        },
        bullish: { DEFAULT: 'var(--bullish)', dark: 'var(--bullish-dark)', light: 'var(--bullish-light)' }, // EMEKLİ → bull
        bearish: { DEFAULT: 'var(--bearish)', dark: 'var(--bearish-dark)', light: 'var(--bearish-light)' }, // EMEKLİ → bear
        warning: { DEFAULT: 'var(--warning)' }, // EMEKLİ → amber
      },
      fontFamily: {
        sans: ['var(--font-sans)', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['var(--font-mono)', 'JetBrains Mono', 'monospace'],
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'glow': 'glow 2s ease-in-out infinite alternate',
        'slide-up': 'slideUp 0.3s ease-out',
        'slide-down': 'slideDown 0.3s ease-out',
        'fade-in': 'fadeIn 0.3s ease-out',
        'scale-in': 'scaleIn 0.2s ease-out',
        'shimmer': 'shimmer 2s infinite',
      },
      keyframes: {
        glow: {
          '0%': { boxShadow: '0 0 5px rgba(59, 130, 246, 0.2)' },
          '100%': { boxShadow: '0 0 20px rgba(59, 130, 246, 0.4)' },
        },
        slideUp: {
          '0%': { transform: 'translateY(10px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        slideDown: {
          '0%': { transform: 'translateY(-10px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        scaleIn: {
          '0%': { transform: 'scale(0.95)', opacity: '0' },
          '100%': { transform: 'scale(1)', opacity: '1' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
      },
      backdropBlur: {
        xs: '2px',
      },
      boxShadow: {
        // ── Design Standards v1.3 owned (Bible §01 craft) ──
        'cta': 'var(--glow-cta)',        // tek CTA glow, opaklık ≤.14
        'e3': 'var(--shadow-e3)',        // YALNIZ E3 overlay
        'cut-lip': 'var(--cut-lip)',     // üst-kenar highlight
        // ── EMEKLİ (glow-bütçe ihlali / kart-gölge yasağı) — P2 util-göç sonrası sil ──
        'glow-sm': '0 0 10px rgba(59, 130, 246, 0.15)',
        'glow-md': '0 0 20px rgba(59, 130, 246, 0.2)',
        'glow-lg': '0 0 30px rgba(59, 130, 246, 0.3)',
        'glow-bullish': '0 0 15px rgba(16, 185, 129, 0.2)',
        'glow-bearish': '0 0 15px rgba(244, 85, 110, 0.2)',
        'card': '0 4px 6px -1px rgba(0, 0, 0, 0.3), 0 2px 4px -2px rgba(0, 0, 0, 0.2)',
        'card-hover': '0 10px 15px -3px rgba(0, 0, 0, 0.4), 0 4px 6px -4px rgba(0, 0, 0, 0.3)',
      },
      // ── Design Standards v1.3 owned ölçek token'ları (Bible §01/§05/§06) ──
      borderRadius: {
        control: 'var(--radius-control)', button: 'var(--radius-button)', input: 'var(--radius-input)',
        card: 'var(--radius-card)', panel: 'var(--radius-panel)', pill: 'var(--radius-pill)', karot: 'var(--radius-karot)',
      },
      zIndex: {
        sticky: 'var(--z-sticky)', dropdown: 'var(--z-dropdown)', modal: 'var(--z-modal)', toast: 'var(--z-toast)', tour: 'var(--z-tour)',
      },
      transitionDuration: {
        micro: 'var(--dur-micro)', state: 'var(--dur-state)', photon: 'var(--dur-photon)', warm: 'var(--dur-warm)',
        settle: 'var(--dur-settle)', route: 'var(--dur-route)', overlay: 'var(--dur-overlay)', stagger: 'var(--stagger)',
      },
      transitionTimingFunction: {
        signal: 'var(--ease-signal)',
      },
    },
  },
  plugins: [],
};
export default config;
