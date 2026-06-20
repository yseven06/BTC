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
          primary: '#020817',
          secondary: '#071126',
          tertiary: '#0B1730',
          glass: 'rgba(7, 17, 38, 0.7)',
          'glass-light': 'rgba(7, 17, 38, 0.4)',
        },
        signal: {
          'strong-buy': '#10B981',
          buy: '#34D399',
          hold: '#F59E0B',
          sell: '#EF4444',
          'strong-sell': '#DC2626',
        },
        accent: {
          primary: '#3B82F6',
          secondary: '#06B6D4',
          glow: 'rgba(59, 130, 246, 0.3)',
          'glow-strong': 'rgba(59, 130, 246, 0.5)',
        },
        text: {
          primary: '#F8FAFC',
          secondary: '#94A3B8',
          muted: '#64748b',
          dark: '#334155',
        },
        border: {
          subtle: 'rgba(148, 163, 184, 0.1)',
          medium: 'rgba(148, 163, 184, 0.2)',
        },
        bullish: { DEFAULT: '#10B981', dark: '#059669', light: '#34D399' },
        bearish: { DEFAULT: '#EF4444', dark: '#DC2626', light: '#F87171' },
        warning: { DEFAULT: '#F59E0B' },
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
