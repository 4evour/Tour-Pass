/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: { 50: '#f0fdf9', 100: '#ccfbef', 200: '#99f6de', 300: '#5ceaca', 400: '#2dd4b4', 500: '#146b5d', 600: '#0d574a', 700: '#0a453b', 800: '#08372f', 900: '#062e28' },
        accent: { 50: '#fff7ed', 100: '#ffedd5', 200: '#fed7aa', 300: '#fdba74', 400: '#fb923c', 500: '#f97316', 600: '#ea580c', 700: '#c2410c', 800: '#9a3412', 900: '#7c2d12' },
      },
    },
  },
  plugins: [],
};
