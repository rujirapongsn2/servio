const config = {
  theme: {
    fontFamily: {
      sans: ['"SF Pro text"', "system-ui", "sans-serif"],
      serif: ['"New York"', "serif"],
    },
    extend: {
      colors: {
        brand: {
          start: "var(--brand-gradient-start)",
          end: "var(--brand-gradient-end)",
          dark: "var(--brand-text-dark)",
        },
      },
      backgroundImage: {
        "brand-gradient": "linear-gradient(90deg, var(--brand-gradient-start), var(--brand-gradient-end))",
      },
    },
  },
  plugins: [],
};

export default config;
