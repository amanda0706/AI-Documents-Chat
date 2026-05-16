import type { Config } from "tailwindcss";

export default {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        ink: "#172033",
        mist: "#f4f7fb",
        line: "#dbe3ee",
        accent: "#3f6ff2",
        warning: "#c8841a",
      },
      boxShadow: {
        panel: "0 18px 48px rgba(23, 32, 51, 0.08)",
      },
    },
  },
  plugins: [],
} satisfies Config;

