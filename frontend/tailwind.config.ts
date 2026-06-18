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
        bg: {
          primary: '#0a0e1a',
          secondary: '#111827',
          tertiary: '#1a2332',
          glass: 'rgba(17, 24, 39, 0.7)',
          'glass-light': 'rgba(17, 24, 39, 0.4)',
        },
        signal: {
          'strong-buy': '#00e676',
          buy: '#4caf50',
          hold: '#ffc107',
          sell: '#ff5252',
          'strong-sell': '#d50000',
        },
        accent: {
          primary: '#6366f1',
          secondary: '#8b5cf6',
          glow: 'rgba(99, 102, 241, 0.3)',
          'glow-strong': 'rgba(99, 102, 241, 0.5)',
        },
        text: {
          primary: '#f1f5f9',
          secondary: '#94a3b8',
          muted: '#64748b',
          dark: '#334155',
        },
        border: {
          subtle: 'rgba(148, 163, 184, 0.1)',
          medium: 'rgba(148, 163, 184, 0.2)',
        },
        bullish: { DEFAULT: '#00e676', dark: '#00c853', light: '#69f0ae' },
        bearish: { DEFAULT: '#ff5252', dark: '#d50000', light: '#ff8a80' },
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
