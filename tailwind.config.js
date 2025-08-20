/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./app/templates/**/*.html",
    "./app/static/**/*.js",
  ],
  theme: { extend: {} },
  plugins: [require("daisyui")],
  daisyui: {
    themes: [
      {
        "brand-light": {
          "primary":   "#0E2A30",  // Teal Blue
          "secondary": "#AFB3A8",  // Smokey Taupe
          "accent":    "#FF542E",  // Vivid Orange
          "neutral":   "#020F13",  // Black
          "base-100":  "#F9F9F9",  // White
          "base-200":  "#D6DFE0",  // Platinum
          "base-300":  "#AFB3A8",  // Smokey Taupe
          "primary-content":   "#F9F9F9",
          "secondary-content": "#020F13",
          "accent-content":    "#020F13",
          "neutral-content":   "#F9F9F9",
          "base-content":      "#020F13",
          "info":    "#3A8FB7",
          "success": "#27856A",
          "warning": "#F59E0B",
          "error":   "#DC2626",
        }
      },
      {
        "brand-teal-surface": {
          "primary":   "#0E2A30",
          "secondary": "#AFB3A8",
          "accent":    "#FF542E",
          "neutral":   "#020F13",
          "base-100":  "#0E2A30",  // Teal background
          "base-200":  "#0B2125",
          "base-300":  "#08191C",
          "primary-content":   "#F9F9F9",
          "secondary-content": "#020F13",
          "accent-content":    "#020F13",
          "neutral-content":   "#F9F9F9",
          "base-content":      "#F9F9F9",
          "info":    "#69B7D1",
          "success": "#35A387",
          "warning": "#FDBA74",
          "error":   "#F87171",
        }
      }
    ],
  },
}
