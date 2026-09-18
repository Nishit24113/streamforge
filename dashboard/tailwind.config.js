/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        forge: {
          50: '#eef7ff',
          100: '#d9ecff',
          200: '#bbdeff',
          300: '#8ccaff',
          400: '#55acff',
          500: '#2e88ff',
          600: '#1766f5',
          700: '#1050e1',
          800: '#1440b6',
          900: '#173a8f',
          950: '#122557',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
    },
  },
  plugins: [],
};
