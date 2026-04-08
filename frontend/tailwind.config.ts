import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        navy: {
          DEFAULT: "#1a2e5a",
          50: "#f0f3fa",
          100: "#d8e0f0",
          600: "#1a2e5a",
          700: "#152449",
          800: "#101b38",
          900: "#0b1226",
        },
        gold: {
          DEFAULT: "#d4af37",
          50: "#fdf8e1",
          100: "#f9ecab",
          200: "#f3dd7a",
          300: "#e8c84a",
          400: "#e8c84a",
          500: "#d4af37",
          600: "#b8952e",
        },
      },
      fontFamily: {
        sans: ["var(--font-noto-sans-kr)", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
