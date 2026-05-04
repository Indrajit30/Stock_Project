import type { Config } from 'tailwindcss'

export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#f0f9ff',
          500: '#0ea5e9',
          900: '#0c4a6e',
        },
        verdict: {
          buy: '#16a34a',
          wait: '#d97706',
          avoid: '#dc2626',
        },
        surface: '#f8fafc',
        border: '#e2e8f0',
      },
    },
  },
} satisfies Config
