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
        signal: {
          'strong-buy': 'var(--signal-strong-buy)',
          buy: 'var(--signal-buy)',
          hold: 'var(--signal-hold)',
          sell: 'var(--signal-sell)',
          'strong-sell': 'var(--signal-strong-sell)',
        },
        accent: {
          primary: 'var(--accent-primary)',
          secondary: 'var(--accent-secondary)',
          glow: 'var(--accent-glow)',
          'glow-strong': 'var(--accent-glow-strong)',
        },
        text: {
          primary: 'var(--text-primary)',
          secondary: 'var(--text-secondary)',
          muted: 'var(--text-muted)',
          dark: 'var(--text-dark)',
        },
        border: {
          subtle: 'var(--border-subtle)',
          medium: 'var(--border-medium)',
        },
        bullish: { DEFAULT: 'var(--bullish)', dark: 'var(--bullish-dark)', light: 'var(--bullish-light)' },
        bearish: { DEFAULT: 'var(--bearish)', dark: 'var(--bearish-dark)', light: 'var(--bearish-light)' },
        warning: { DEFAULT: 'var(--warning)' },
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
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
          '0%': { boxShadow: '0 0 5px rgba(99, 102, 241, 0.2)' },
          '100%': { boxShadow: '0 0 20px rgba(99, 102, 241, 0.4)' },
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
        'glow-sm': '0 0 10px rgba(99, 102, 241, 0.15)',
        'glow-md': '0 0 20px rgba(99, 102, 241, 0.2)',
        'glow-lg': '0 0 30px rgba(99, 102, 241, 0.3)',
        'glow-bullish': '0 0 15px rgba(0, 230, 118, 0.2)',
        'glow-bearish': '0 0 15px rgba(255, 82, 82, 0.2)',
        'card': '0 4px 6px -1px rgba(0, 0, 0, 0.3), 0 2px 4px -2px rgba(0, 0, 0, 0.2)',
        'card-hover': '0 10px 15px -3px rgba(0, 0, 0, 0.4), 0 4px 6px -4px rgba(0, 0, 0, 0.3)',
      },
    },
  },
  plugins: [],
};
export default config;
