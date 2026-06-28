/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        surface: "#0f1419",
        panel: "#1a2332",
        border: "#2a3544",
        muted: "#8b9cb3",
        accept: "#22c55e",
        flag: "#eab308",
        reject: "#ef4444",
        "soft-accept": "#86efac",
        "soft-flag": "#fde68a",
        "soft-reject": "#fca5a5",
      },
      boxShadow: {
        glowGreen: "0 0 20px rgba(34, 197, 94, 0.65), 0 0 40px rgba(34, 197, 94, 0.25)",
        glowYellow: "0 0 20px rgba(234, 179, 8, 0.65), 0 0 40px rgba(234, 179, 8, 0.25)",
        glowRed: "0 0 20px rgba(239, 68, 68, 0.65), 0 0 40px rgba(239, 68, 68, 0.25)",
        softGlowGreen: "0 0 28px rgba(134, 239, 172, 0.45), 0 0 56px rgba(134, 239, 172, 0.15)",
        softGlowYellow: "0 0 28px rgba(253, 230, 138, 0.45), 0 0 56px rgba(253, 230, 138, 0.15)",
        softGlowRed: "0 0 28px rgba(252, 165, 165, 0.45), 0 0 56px rgba(252, 165, 165, 0.15)",
      },
    },
  },
  plugins: [],
};
