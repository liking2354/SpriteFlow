import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx,jsx,js}"],
  theme: {
    extend: {
      colors: {
        bg: {
          0: "var(--bg-0)",
          1: "var(--bg-1)",
          2: "var(--bg-2)",
          3: "var(--bg-3)",
        },
        line: {
          DEFAULT: "var(--line)",
          soft: "var(--line-soft)",
        },
        txt: {
          0: "var(--txt-0)",
          1: "var(--txt-1)",
          2: "var(--txt-2)",
          3: "var(--txt-3)",
        },
        acc: "var(--acc)",
        cyan: "var(--cyan)",
        violet: "var(--violet)",
        pink: "var(--pink)",
        amber: "var(--amber)",
        green: "var(--green)",
      },
      borderRadius: {
        s: "8px",
        m: "12px",
        l: "18px",
      },
      fontFamily: {
        sans: ["var(--font-sans)"],
        mono: ["var(--font-mono)"],
      },
      boxShadow: {
        glow: "0 0 16px var(--acc-glow)",
        node: "0 8px 30px #00000066",
      },
    },
  },
  plugins: [],
};

export default config;
