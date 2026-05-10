/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        scu: {
          red: "var(--scu-red)",
          "dark-red": "var(--scu-dark-red)",
          white: "var(--scu-white)",
          gray: "var(--scu-gray)",
          text: "var(--scu-text)",
        },
      },
    },
  },
  plugins: [],
};
