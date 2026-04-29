/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        base: "#0b1020",
        panel: "#111a2f",
        accent: "#7dd3fc",
        peach: "#fdba74",
        mint: "#6ee7b7"
      },
      boxShadow: {
        glow: "0 10px 30px rgba(125, 211, 252, 0.25)"
      }
    }
  },
  plugins: []
};
