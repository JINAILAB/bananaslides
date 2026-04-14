/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: "#f8f9fa",
        surface: "#f8f9fa",
        "surface-low": "#f3f4f5",
        "surface-high": "#e7e8e9",
        primary: "#745b00",
        "primary-bright": "#f2c94c",
        "primary-soft": "#fff4cf",
        tertiary: "#006783",
        outline: "#d0c5af",
        ink: "#191c1d",
        muted: "#5d625f",
      },
      fontFamily: {
        headline: ["Manrope", "sans-serif"],
        body: ["Inter", "sans-serif"],
      },
      boxShadow: {
        soft: "0 16px 40px rgba(17, 24, 39, 0.08)",
      },
      borderRadius: {
        "4xl": "2rem",
      },
      backgroundImage: {
        hero: "linear-gradient(135deg, #745b00 0%, #f2c94c 100%)",
      },
    },
  },
  plugins: [],
};
