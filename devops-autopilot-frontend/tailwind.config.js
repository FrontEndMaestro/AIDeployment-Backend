export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        cyan: {
          50: '#ecf7ff',
          400: '#06b6d4',
          500: '#06b6d4',
          600: '#0891b2',
        },
        gray: {
          750: '#1a232e',
        }
      }
    },
  },
  plugins: [],
}