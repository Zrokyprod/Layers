/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'Consolas', 'monospace'],
      },
      colors: {
        canvas: '#f6f7f9',
        'canvas-soft': '#eceff3',
        panel: '#ffffff',
        'panel-solid': '#ffffff',
        'panel-soft': '#f1f4f7',
        'panel-border': '#dce3eb',
        primary: '#101216',
        secondary: '#4c5563',
        tertiary: '#828b99',
        accent: '#635bff',
        gold: '#e4578d',
        violet: '#6d5dfc',
        steel: '#4e647f',
        danger: '#d9465f',
        ok: '#3d65d8',
        warning: '#b7791f',
        success: '#16a34a',
        'success-soft': '#f0fdf4',
      },
      boxShadow: {
        premium: '0 18px 55px -30px rgba(17, 24, 39, 0.28), 0 1px 1px rgba(17, 24, 39, 0.04)',
        'premium-hover': '0 30px 80px -38px rgba(37, 99, 235, 0.3), 0 12px 30px -24px rgba(17, 24, 39, 0.28)',
        'inner-light': 'inset 0 1px 0 0 rgba(255, 255, 255, 0.9)',
        'blue-glow': '0 0 0 1px rgba(37, 99, 235, 0.18), 0 18px 55px rgba(37, 99, 235, 0.13)',
        'gold-glow': '0 0 0 1px rgba(228, 87, 141, 0.2), 0 18px 55px rgba(228, 87, 141, 0.12)',
      },
      backgroundImage: {
        'signal-grid': 'linear-gradient(rgba(17,24,39,.055) 1px, transparent 1px), linear-gradient(90deg, rgba(17,24,39,.055) 1px, transparent 1px)',
        'panel-sheen': 'linear-gradient(135deg, rgba(255,255,255,.95), rgba(246,248,251,.72) 38%, rgba(37,99,235,.08))',
      },
      keyframes: {
        scan: {
          '0%': { transform: 'translateY(-110%)' },
          '100%': { transform: 'translateY(110%)' },
        },
        flowX: {
          '0%': { transform: 'translateX(-28%)', opacity: '0' },
          '12%': { opacity: '1' },
          '88%': { opacity: '1' },
          '100%': { transform: 'translateX(128%)', opacity: '0' },
        },
        sweep: {
          '0%': { transform: 'rotate(0deg)' },
          '100%': { transform: 'rotate(360deg)' },
        },
        floatSoft: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-12px)' },
        },
        shimmer: {
          '0%': { backgroundPosition: '200% 0' },
          '100%': { backgroundPosition: '-200% 0' },
        },
      },
      animation: {
        scan: 'scan 4.8s linear infinite',
        flowX: 'flowX 4.6s ease-in-out infinite',
        sweep: 'sweep 12s linear infinite',
        floatSoft: 'floatSoft 7s ease-in-out infinite',
        shimmer: 'shimmer 7s linear infinite',
      },
    },
  },
  plugins: [],
}
