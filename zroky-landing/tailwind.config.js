/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter Variable', 'Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'Consolas', 'monospace'],
      },
      colors: {
        // Monochrome system: white / grey / black only.
        ink: '#0A0A0A',          // near-black canvas
        'ink-2': '#0F0F10',
        surface: '#141416',
        'surface-2': '#1A1A1D',
        line: 'rgba(255,255,255,0.10)',
        'line-strong': 'rgba(255,255,255,0.20)',
        primary: '#FAFAFA',       // text
        secondary: 'rgba(255,255,255,0.70)',
        tertiary: 'rgba(255,255,255,0.48)',
        // Semantic (used sparingly, "baki colours zarurat padne par")
        discovered: '#A78BFA',    // violet — Zroky found this
        verified: '#34D399',      // green — proven
        blocked: '#F87171',       // red — blocked/failure
        review: '#FBBF24',        // amber — review/watching
      },
      boxShadow: {
        card: '0 1px 0 rgba(255,255,255,0.05) inset, 0 24px 60px -36px rgba(0,0,0,0.8)',
        'card-hover': '0 1px 0 rgba(255,255,255,0.10) inset, 0 36px 90px -40px rgba(0,0,0,0.9)',
        glow: '0 0 0 1px rgba(255,255,255,0.08), 0 30px 80px -50px rgba(255,255,255,0.25)',
      },
      backgroundImage: {
        'grid-mono': 'linear-gradient(rgba(255,255,255,.05) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.05) 1px, transparent 1px)',
      },
      keyframes: {
        floatSoft: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-10px)' },
        },
        shimmer: {
          '0%': { backgroundPosition: '200% 0' },
          '100%': { backgroundPosition: '-200% 0' },
        },
        drawLine: {
          '0%': { strokeDashoffset: '1' },
          '100%': { strokeDashoffset: '0' },
        },
        pulseDot: {
          '0%, 100%': { opacity: '0.4', transform: 'scale(0.9)' },
          '50%': { opacity: '1', transform: 'scale(1.1)' },
        },
      },
      animation: {
        floatSoft: 'floatSoft 7s ease-in-out infinite',
        shimmer: 'shimmer 8s linear infinite',
        pulseDot: 'pulseDot 2.4s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
