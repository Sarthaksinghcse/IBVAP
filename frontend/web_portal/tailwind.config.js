/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {

    extend: {
      colors: {
        ibvap: {
          bg:        '#0a0e1a',
          surface:   '#0f1629',
          'surface-2': '#141e33',
          border:    '#1e2d4a',
          'border-2': '#253a5e',
          accent:    '#1d6af5',
          'accent-hover': '#2d7aff',
          'accent-dim': 'rgba(29,106,245,0.15)',
        },
        threat: {
          critical: '#ef4444',
          'critical-bg': 'rgba(239,68,68,0.1)',
          'critical-border': 'rgba(239,68,68,0.35)',
          high:     '#f97316',
          'high-bg': 'rgba(249,115,22,0.1)',
          'high-border': 'rgba(249,115,22,0.35)',
          medium:   '#eab308',
          'medium-bg': 'rgba(234,179,8,0.1)',
          'medium-border': 'rgba(234,179,8,0.35)',
          low:      '#22c55e',
          'low-bg': 'rgba(34,197,94,0.1)',
          'low-border': 'rgba(34,197,94,0.35)',
          none:     '#64748b',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', '"Fira Code"', 'monospace'],
      },
      animation: {
        'live-pulse': 'livePulse 1.5s ease-in-out infinite',
        'bbox-critical': 'bboxCritical 1s ease-in-out infinite',
        'scanline': 'scanline 5s linear infinite',
        'fade-in': 'fadeIn 0.3s ease-out',
        'slide-in': 'slideIn 0.3s ease-out',
        'glow': 'glow 2s ease-in-out infinite',
      },
      keyframes: {
        livePulse: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.3' },
        },
        bboxCritical: {
          '0%, 100%': { borderColor: 'rgba(239,68,68,1)', boxShadow: '0 0 8px rgba(239,68,68,0.4)' },
          '50%': { borderColor: 'rgba(239,68,68,0.3)', boxShadow: '0 0 0px transparent' },
        },
        scanline: {
          '0%': { transform: 'translateY(-100%)' },
          '100%': { transform: 'translateY(200%)' },
        },
        fadeIn: {
          '0%': { opacity: '0', transform: 'translateY(4px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        slideIn: {
          '0%': { opacity: '0', transform: 'translateX(-8px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
        glow: {
          '0%, 100%': { boxShadow: '0 0 4px rgba(29,106,245,0.3)' },
          '50%': { boxShadow: '0 0 16px rgba(29,106,245,0.6)' },
        },
      },
      boxShadow: {
        'card': '0 1px 3px rgba(0,0,0,0.4), 0 0 0 1px rgba(30,45,74,0.6)',
        'card-hover': '0 4px 16px rgba(0,0,0,0.5), 0 0 0 1px rgba(29,106,245,0.3)',
        'alert-critical': '0 0 0 1px rgba(239,68,68,0.3), inset 0 0 20px rgba(239,68,68,0.03)',
        'glow-accent': '0 0 20px rgba(29,106,245,0.2)',
      },
    },
  },
  plugins: [
    function ({ addVariant }) {
      addVariant('light', ['html.light &', 'html[data-theme="light"] &', '.light &']);
    },
  ],
}

