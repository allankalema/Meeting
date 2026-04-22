/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./attendance/**/*.py",
    "./meeting/**/*.py",
  ],
  theme: {
    extend: {
      colors: {
        "rotary-blue": {
          DEFAULT: "#17458F",
          600: "#123A79",
          700: "#0F3167",
        },
        "rotary-gold": {
          DEFAULT: "#F7A81B",
          500: "#F7A81B",
          600: "#DD930E",
        },
      },
    },
  },
  plugins: [],
};
