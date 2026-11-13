/** @type {import('tailwindcss').Config} */

// Brand palette: coral #F96246 is THE main colour (actions, selection, highlights, hero).
// Sand #E9D3C3 and the warm "ink" neutrals carry surfaces and text. Deep teal #486061 and
// mist #EFFEFC are used sparingly, for small accents only. Brown and gold support the sand tones.
// The stock slate / emerald / rose / amber / sky / indigo scales are remapped so every
// existing utility class picks up the theme: slate is now the warm ink scale, not teal.

const teal = {
  50: "#F3F6F6",
  100: "#E4EBEB",
  200: "#C9D5D5",
  300: "#A4B6B6",
  400: "#7B9394",
  500: "#5D7778",
  600: "#486061",
  700: "#3B5051",
  800: "#2E3F40",
  900: "#223132",
  950: "#162122",
};

// Warm neutral for text, borders and dark surfaces (a brown-black, so teal stays an accent).
const ink = {
  50: "#FAF7F5",
  100: "#F3EEEA",
  200: "#E6DDD7",
  300: "#D1C5BD",
  400: "#AC9E95",
  500: "#85776E",
  600: "#665A52",
  700: "#4D433D",
  800: "#362E2A",
  900: "#251F1C",
  950: "#171210",
};

const coral = {
  50: "#FFF4F1",
  100: "#FEE6DF",
  200: "#FDC9BB",
  300: "#FCA48F",
  400: "#FA8068",
  500: "#F96246",
  600: "#E54B2F",
  700: "#BF3B23",
  800: "#983220",
  900: "#7B2C1E",
};

const sand = {
  50: "#FCF8F5",
  100: "#F6ECE4",
  200: "#E9D3C3",
  300: "#DEBEA8",
  400: "#CDA285",
  500: "#B58665",
  600: "#966B4D",
  700: "#77543C",
  800: "#5B412F",
  900: "#433024",
};

const gold = {
  50: "#FBF7EB",
  100: "#F5EACB",
  200: "#EDD89C",
  300: "#E3C46D",
  400: "#D4AC47",
  500: "#BE9536",
  600: "#9C782A",
  700: "#7C5E22",
  800: "#614A1D",
  900: "#4B3918",
  950: "#30240E",
};

const success = {
  50: "#EEF7F3",
  100: "#D6EEE4",
  200: "#AFDCC9",
  300: "#80C4A8",
  400: "#52A887",
  500: "#358D6D",
  600: "#287458",
  700: "#215E48",
  800: "#1B4A3A",
  900: "#163D30",
};

const danger = {
  50: "#FDF2EF",
  100: "#F9DFD8",
  200: "#F1BBAD",
  300: "#E5917C",
  400: "#D76A51",
  500: "#C4513A",
  600: "#A9402C",
  700: "#8C3426",
  800: "#712C21",
  900: "#5C261D",
};

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        slate: ink,
        ink,
        teal,
        coral,
        sand,
        gold,
        brown: sand,
        emerald: success,
        rose: danger,
        amber: gold,
        sky: teal,
        indigo: sand,
        snow: "#FBFCFC",
        mist: "#EFFEFC",
      },
      fontFamily: {
        sans: ["Manrope", "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        display: ["Sora", "Manrope", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      boxShadow: {
        soft: "0 1px 2px rgba(37, 31, 28, 0.04), 0 4px 16px -6px rgba(37, 31, 28, 0.10)",
        lift: "0 2px 4px rgba(37, 31, 28, 0.05), 0 18px 36px -14px rgba(37, 31, 28, 0.26)",
        glow: "0 10px 30px -10px rgba(249, 98, 70, 0.55)",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(14px)" },
          "100%": { opacity: "1", transform: "none" },
        },
        "fade-in": { "0%": { opacity: "0" }, "100%": { opacity: "1" } },
        shimmer: { "0%": { backgroundPosition: "-200% 0" }, "100%": { backgroundPosition: "200% 0" } },
        float: { "0%, 100%": { transform: "translateY(0)" }, "50%": { transform: "translateY(-10px)" } },
        "needle-seek": {
          "0%": { transform: "rotate(-40deg)" },
          "30%": { transform: "rotate(65deg)" },
          "55%": { transform: "rotate(10deg)" },
          "75%": { transform: "rotate(38deg)" },
          "100%": { transform: "rotate(-40deg)" },
        },
        "spin-slow": { "0%": { transform: "rotate(0deg)" }, "100%": { transform: "rotate(360deg)" } },
        "pulse-ring": {
          "0%": { transform: "scale(0.85)", opacity: "0.7" },
          "100%": { transform: "scale(1.6)", opacity: "0" },
        },
        marquee: { "0%": { transform: "translateX(0)" }, "100%": { transform: "translateX(-50%)" } },
        "gradient-pan": {
          "0%, 100%": { backgroundPosition: "0% 50%" },
          "50%": { backgroundPosition: "100% 50%" },
        },
        "dot-bounce": {
          "0%, 80%, 100%": { transform: "translateY(0)", opacity: "0.4" },
          "40%": { transform: "translateY(-5px)", opacity: "1" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.55s cubic-bezier(0.22, 1, 0.36, 1) backwards",
        "fade-in": "fade-in 0.4s ease-out backwards",
        shimmer: "shimmer 1.6s linear infinite",
        float: "float 6s ease-in-out infinite",
        "needle-seek": "needle-seek 2.4s cubic-bezier(0.45, 0, 0.25, 1) infinite",
        "spin-slow": "spin-slow 18s linear infinite",
        "pulse-ring": "pulse-ring 1.8s cubic-bezier(0.22, 1, 0.36, 1) infinite",
        marquee: "marquee 38s linear infinite",
        "gradient-pan": "gradient-pan 10s ease infinite",
        "dot-bounce": "dot-bounce 1.2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
